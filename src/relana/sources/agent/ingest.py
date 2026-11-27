"""エージェントが読み取ったカレンダーを取り込む（方式E-2）。

コーディングエージェントのカレンダー連携は、利用者自身の権限で動く。
到達範囲は内部OAuthクライアント方式と同じであり、Google Cloud プロジェクトも
OAuth クライアントの登録も要らない。人事担当者にとって最も負担が軽い経路。

エージェントは**最小限の形**で書き出すだけでよい。重複排除・会議室の除去・
会議種別の推定といった正規化は、ここから先を relana が受け持つ。

    {"id": "...", "start": "2026-10-08T10:00:00+09:00", "end": "...",
     "organizer": "ichikawa@example.co.jp",
     "attendees": [{"email": "ou@example.co.jp", "responseStatus": "accepted"}],
     "recurring": true, "title": "1on1 kaishi / takafumi"}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REQUIRED = ("start", "attendees")


@dataclass
class IngestIssue:
    line: int
    code: str
    message: str
    fix: str


@dataclass
class IngestResult:
    raw_events: list[dict] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    lines_read: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues


def to_gcal_shape(rec: dict[str, Any], index: int) -> dict[str, Any]:
    """エージェントが書いた最小形を、正規化が受け取れる形に変換する。"""
    attendees = []
    for a in rec.get("attendees") or []:
        if isinstance(a, str):
            attendees.append({"email": a, "responseStatus": "needsAction"})
        else:
            attendees.append(
                {
                    "email": a.get("email", ""),
                    "responseStatus": a.get("responseStatus") or a.get("response") or "needsAction",
                    **({"resource": True} if a.get("resource") else {}),
                }
            )
    organizer = rec.get("organizer")
    if isinstance(organizer, dict):
        organizer = organizer.get("email", "")

    out: dict[str, Any] = {
        "id": str(rec.get("id") or f"agent_{index:06d}"),
        "iCalUID": str(rec.get("uid") or rec.get("id") or f"agent_{index:06d}"),
        "start": {"dateTime": rec["start"]},
        "end": {"dateTime": rec.get("end") or rec["start"]},
        "organizer": {"email": organizer or (attendees[0]["email"] if attendees else "")},
        "attendees": attendees,
    }
    if rec.get("recurring"):
        out["recurringEventId"] = out["iCalUID"]
    if rec.get("title"):
        out["summary"] = rec["title"]
    return out


def read_jsonl(path: Path) -> IngestResult:
    res = IngestResult()
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        res.lines_read += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            res.issues.append(
                IngestIssue(i, "E_BAD_JSON", f"JSON として読めません: {e.msg}",
                            "1行に1件のJSONオブジェクトを書いてください。")
            )
            continue
        if not isinstance(rec, dict):
            res.issues.append(
                IngestIssue(i, "E_NOT_OBJECT", "オブジェクトではありません。",
                            '{"start": ..., "attendees": [...]} の形にしてください。')
            )
            continue
        missing = [k for k in REQUIRED if not rec.get(k)]
        if missing:
            res.issues.append(
                IngestIssue(
                    i, "E_MISSING_FIELD", f"必須項目がありません: {', '.join(missing)}",
                    "start（開始日時）と attendees（参加者）は必ず入れてください。"
                    "参加者が分からない予定は分析に使えないので、書き出さなくて構いません。",
                )
            )
            continue
        res.raw_events.append(to_gcal_shape(rec, i))
    return res


def coverage_hint(raw_events: Iterable[dict]) -> dict[str, Any]:
    """どこまで集めれば足りるかを判断する材料。

    1人分のカレンダーを読むと、その人の会議の全参加者どうしの関係が得られる。
    したがって、観測できた人数は読んだカレンダー数より大幅に多くなる。
    """
    people: set[str] = set()
    pairs = 0
    for ev in raw_events:
        emails = [a["email"] for a in ev.get("attendees", []) if a.get("email")]
        people.update(emails)
        n = len(emails)
        pairs += n * (n - 1) // 2
    return {"people_observed": len(people), "pair_observations": pairs}


def domain_breakdown(raw_events: Iterable[dict]) -> dict[str, Any]:
    """参加者のメールドメインの内訳。

    名簿を用意させない以上、どこまでが社内かもデータから決める必要がある。
    ただし**件数だけで複数の社内ドメインを言い当てるのは信用できない**ため、
    最頻のドメインのみを社内とみなし、紛らわしいものは確認を促す。
    """
    from collections import Counter

    counts: Counter = Counter()
    for ev in raw_events:
        for a in ev.get("attendees", []):
            email = (a.get("email") or "").lower()
            if "@" in email and "resource.calendar.google.com" not in email:
                counts[email.split("@")[-1]] += 1
    total = sum(counts.values())
    if not total:
        return {"internal": [], "ambiguous": [], "counts": {}}

    top, top_count = counts.most_common(1)[0]
    ambiguous = [
        {"domain": d, "share": round(c / total, 3)}
        for d, c in counts.most_common()[1:]
        if c / total >= AMBIGUOUS_SHARE
    ]
    return {
        "internal": [top],
        "ambiguous": ambiguous,
        "counts": dict(counts.most_common(10)),
        "top_share": round(top_count / total, 3),
    }


def detect_internal_domains(raw_events: Iterable[dict]) -> list[str]:
    """社内とみなすドメイン。複数ある場合は --internal-domain で明示してもらう。"""
    return domain_breakdown(raw_events)["internal"]


# ---------------------------------------------------------------- 収集の進め方

SIDECAR = ".relana-read-calendars.json"
# これを超える割合を占めるドメインは、社内かどうか確認を促す
AMBIGUOUS_SHARE = 0.2


def record_read(out: Path, calendars: Iterable[str]) -> list[str]:
    """どのカレンダーを読んだかを記録する。次に誰を読むべきかの判断に使う。"""
    path = out.parent / SIDECAR
    known = set(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else set()
    known.update(c.lower() for c in calendars if c)
    path.write_text(json.dumps(sorted(known), ensure_ascii=False), encoding="utf-8")
    return sorted(known)


def read_calendars(out: Path) -> list[str]:
    path = out.parent / SIDECAR
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def suggest_next(interactions, already_read: list[str], limit: int = 10) -> dict[str, Any]:
    """次に読むべきカレンダーを提案する。

    1人分のカレンダーを読むと、その人の会議の全参加者どうしの関係が得られる。
    したがって全員分を読む必要はない。多くの会議に現れる人ほど、読むと
    得られる関係が多い。
    """
    from collections import Counter

    read = {c.lower() for c in already_read}
    appearances: Counter = Counter()
    one_on_ones: Counter = Counter()
    for ev in interactions:
        att = [a for a in ev.attendees if not a.startswith("ext:")]
        for pid in att:
            appearances[pid] += 1
            if len(att) == 2:
                one_on_ones[pid] += 1

    unread = [
        {
            "calendar": pid,
            "appearances": appearances[pid],
            "one_on_ones_seen": one_on_ones[pid],
            "reason": _reason(appearances[pid], one_on_ones[pid]),
        }
        for pid in appearances
        if pid.lower() not in read
    ]
    unread.sort(key=lambda r: -r["appearances"])

    observed = len(appearances)
    return {
        "calendars_read": len(read),
        "people_observed": observed,
        "leverage": round(observed / len(read), 1) if read else 0.0,
        "suggestions": unread[:limit],
        "note": (
            "1人分を読むと、その人の会議の全参加者どうしの関係が得られます。"
            "全員分を読む必要はありません。集計できた人の割合は `relana doctor` で確認してください。"
        ),
    }


def _reason(appearances: int, dyads: int) -> str:
    if dyads >= 3:
        return "1on1 が多く、まだ見えていない二者関係を持っている可能性が高い"
    if appearances >= 10:
        return "多くの会議に出ており、読むと得られる関係が多い"
    return "追加の関係が見込める"

"""入力の検証（原則3: 自己修復可能なエラー）。

エラーは1件ずつ返さず**まとめて返す**。1件直すたびに往復させると、
エージェントも人間も消耗する。各エラーには何が期待値で何が来たか、
そして次に何をすべきかを必ず含める。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

REQUIRED_INTERACTION = ["event_id", "ts", "actor_id", "target_ids"]
REQUIRED_PERSON = ["person_id"]

# よくある別名 -> 正しい列名。エージェントが直せるよう候補を提示する
ALIASES = {
    "actor_id": ["from", "from_user", "organizer", "organizer_id", "sender", "host"],
    "target_ids": ["to", "to_user", "attendees", "participants", "targets", "guests"],
    "ts": ["timestamp", "datetime", "start", "start_time", "date", "occurred_at"],
    "event_id": ["id", "uid", "meeting_id"],
    "person_id": ["id", "user_id", "employee_id"],
    "email": ["mail", "email_address", "mail_address"],
    "dept": ["department", "division", "部門", "部署"],
    "team": ["group", "unit", "チーム"],
}


@dataclass
class Issue:
    code: str
    severity: str  # error | warning
    message: str
    fix: str
    row: int | None = None
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "fix": self.fix,
            "row": self.row,
            "column": self.column,
        }


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)
    rows_checked: int = 0

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rows_checked": self.rows_checked,
            "error_count": len(self.errors),
            "warning_count": len(self.issues) - len(self.errors),
            "issues": [i.to_dict() for i in self.issues],
        }


def _suggest(missing: str, present: list[str]) -> str:
    lowered = {c.lower(): c for c in present}
    for alias in ALIASES.get(missing, []):
        if alias.lower() in lowered:
            return f"'{lowered[alias.lower()]}' を '{missing}' にリネームしてください。"
    return (
        f"'{missing}' 列を追加してください。"
        f"（いま存在する列: {', '.join(present) if present else 'なし'}）"
    )


def validate_persons(rows: list[dict]) -> ValidationResult:
    res = ValidationResult(rows_checked=len(rows))
    if not rows:
        res.issues.append(
            Issue("E_EMPTY_PERSONS", "error", "persons に行がありません。", "1行以上の名簿を用意してください。")
        )
        return res

    cols = list(rows[0].keys())
    for req in REQUIRED_PERSON:
        if req not in cols:
            res.issues.append(
                Issue("E_MISSING_COLUMN", "error", f"必須列 '{req}' がありません。", _suggest(req, cols), column=req)
            )
    for soft in ("dept", "team"):
        if soft not in cols:
            res.issues.append(
                Issue(
                    "W_MISSING_GROUPING",
                    "warning",
                    f"'{soft}' 列がありません。この軸での集計（サイロ診断・チーム分析）ができません。",
                    _suggest(soft, cols),
                    column=soft,
                )
            )

    seen: dict[str, int] = {}
    for i, r in enumerate(rows, start=2):  # 1行目はヘッダ
        pid = (r.get("person_id") or "").strip()
        if not pid:
            res.issues.append(Issue("E_EMPTY_ID", "error", "person_id が空です。", "一意なIDを入れてください。", row=i))
            continue
        if pid in seen:
            res.issues.append(
                Issue(
                    "E_DUPLICATE_ID",
                    "error",
                    f"person_id '{pid}' が重複しています（{seen[pid]}行目と{i}行目）。",
                    "person_id は一意である必要があります。重複行を統合または削除してください。",
                    row=i,
                )
            )
        seen[pid] = i
    return res


def validate_interactions(rows: list[dict], person_ids: set[str] | None = None) -> ValidationResult:
    res = ValidationResult(rows_checked=len(rows))
    if not rows:
        res.issues.append(
            Issue(
                "E_NO_INTERACTIONS",
                "error",
                "相互作用イベントが0件です。",
                "収集結果を確認してください。全件が除外された場合は、"
                "normalize の設定（drop_declined / min_attendees）を見直してください。",
            )
        )
        return res

    cols = list(rows[0].keys())
    for req in REQUIRED_INTERACTION:
        if req not in cols:
            res.issues.append(
                Issue("E_MISSING_COLUMN", "error", f"必須列 '{req}' がありません。", _suggest(req, cols), column=req)
            )
    if res.errors:
        return res  # 列が無い状態で行検査しても意味がない

    seen_ids: dict[str, int] = {}
    unknown: set[str] = set()
    bad_ts = 0
    for i, r in enumerate(rows, start=2):
        eid = str(r.get("event_id") or "").strip()
        if not eid:
            res.issues.append(Issue("E_EMPTY_ID", "error", "event_id が空です。", "一意なIDを入れてください。", row=i))
        elif eid in seen_ids:
            res.issues.append(
                Issue(
                    "E_DUPLICATE_ID",
                    "error",
                    f"event_id '{eid}' が重複しています（{seen_ids[eid]}行目と{i}行目）。",
                    "同じ会議を複数のカレンダーから取得すると、この重複が出ます。"
                    "iCalUID で重複排除してください。",
                    row=i,
                )
            )
        else:
            seen_ids[eid] = i

        try:
            datetime.fromisoformat(str(r.get("ts", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            bad_ts += 1
            if bad_ts <= 5:
                res.issues.append(
                    Issue(
                        "E_BAD_TIMESTAMP",
                        "error",
                        f"ts '{r.get('ts')}' を日時として読めません。",
                        "ISO 8601 形式（例: 2026-01-06T10:00:00Z）にしてください。",
                        row=i,
                        column="ts",
                    )
                )

        targets = r.get("target_ids")
        if isinstance(targets, str):
            targets = [t for t in targets.split("|") if t]
        if not targets:
            res.issues.append(
                Issue(
                    "E_NO_TARGET",
                    "error",
                    "target_ids が空です。相手のいないイベントは関係を表しません。",
                    "参加者が1名のイベント（自分のブロック・休暇）は取り込み前に除外してください。",
                    row=i,
                )
            )
        if person_ids is not None:
            for pid in [r.get("actor_id"), *(targets or [])]:
                if pid and not str(pid).startswith("ext:") and pid not in person_ids:
                    unknown.add(str(pid))

    if bad_ts > 5:
        res.issues.append(
            Issue(
                "E_BAD_TIMESTAMP",
                "error",
                f"ほかにも {bad_ts - 5} 件、日時として読めない ts があります。",
                "ISO 8601 形式に揃えてください。",
                column="ts",
            )
        )
    if unknown:
        sample = ", ".join(sorted(unknown)[:8])
        res.issues.append(
            Issue(
                "W_UNKNOWN_PERSON",
                "warning",
                f"persons に無いIDが {len(unknown)} 件あります（例: {sample}）。",
                "名簿に追加するか、外部の相手であれば 'ext:' で始まるIDにしてください。"
                "放置すると部門が『(不明)』として集計されます。",
            )
        )
    return res

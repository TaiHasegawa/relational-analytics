"""名簿のレビューと、並列収集のためのバッチ分割。

名簿を利用者に用意させない代わりに、**収集データから作った名簿を見せて確認してもらう**。
実測では、単一の全体MTGから作った名簿が全社の55%しかなく、確認の機会が無いまま
分析まで進んでしまった。確認を工程として入れることでそれを防ぐ。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import Interaction, Person

BATCH_SIZE = 12


@dataclass
class RosterEntry:
    person_id: str
    display_name: str
    dept: str = ""
    team: str = ""
    role: str = ""
    meetings: int = 0
    one_on_ones: int = 0
    flags: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "email": self.person_id,
            "display_name": self.display_name,
            "dept": self.dept,
            "team": self.team,
            "role": self.role,
            "_meetings": self.meetings,
            "_one_on_ones": self.one_on_ones,
            "_flags": "|".join(self.flags),
        }


@dataclass
class RosterReview:
    entries: list[RosterEntry]
    headcount: int | None = None

    @property
    def by_dept(self) -> dict[str, list[RosterEntry]]:
        groups: dict[str, list[RosterEntry]] = defaultdict(list)
        for e in self.entries:
            groups[e.dept or "（所属が分かりませんでした）"].append(e)
        return dict(sorted(groups.items(), key=lambda kv: (kv[0].startswith("（"), -len(kv[1]))))

    @property
    def missing(self) -> int | None:
        return self.headcount - len(self.entries) if self.headcount else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "people": len(self.entries),
            "headcount": self.headcount,
            "missing": self.missing,
            "departments": {
                dept: [e.to_row() for e in members] for dept, members in self.by_dept.items()
            },
            "flagged": [e.to_row() for e in self.entries if e.flags],
        }


def build(
    interactions: list[Interaction],
    persons: list[Person] | None = None,
    headcount: int | None = None,
) -> RosterReview:
    """収集データから、確認用の名簿を組み立てる。"""
    from .group_address import is_suspected_group

    attrs = {p.person_id: p for p in (persons or [])}
    meetings: Counter = Counter()
    dyads: Counter = Counter()
    for ev in interactions:
        att = [a for a in ev.attendees if not a.startswith("ext:")]
        for pid in att:
            meetings[pid] += 1
            if len(att) == 2:
                dyads[pid] += 1

    entries: list[RosterEntry] = []
    for pid, n in meetings.items():
        p = attrs.get(pid)
        local = pid.split("@")[0].lower()
        flags: list[str] = []
        # 確実なグループは正規化で既に落ちている。ここに残るのは判断が要るもの。
        # 名前だけで疑うと pr.tanaka@ のような実在の人を誤判定するため、
        # **1on1 が一度も無い**という振る舞いを主判定にする。
        if n >= 5 and dyads[pid] == 0:
            hint = "（名前もグループ的）" if is_suspected_group(pid) else ""
            flags.append(f"1on1 が一度も無い{hint}。グループアドレスの可能性")
        if n <= 2:
            flags.append("会議が極端に少ない")
        if p is None or not p.dept:
            flags.append("所属が不明")

        entries.append(
            RosterEntry(
                person_id=pid,
                display_name=(p.display_name if p and p.display_name else local),
                dept=(p.dept if p else ""),
                team=(p.team if p else ""),
                role=(p.role if p else ""),
                meetings=n,
                one_on_ones=dyads[pid],
                flags=flags,
            )
        )
    entries.sort(key=lambda e: (e.dept or "zzz", e.team, -e.meetings))
    return RosterReview(entries=entries, headcount=headcount)


def render_text(review: RosterReview) -> str:
    """利用者に見せる形。部署ごとに並べ、確認すべき点を分けて示す。"""
    out: list[str] = []
    a = out.append
    a("カレンダーから、次の組織構成を読み取りました。")
    a("")
    for dept, members in review.by_dept.items():
        mgr = next((m for m in members if m.role == "マネジャー"), None)
        head = f"■ {dept}（{len(members)}名）"
        if mgr:
            head += f"　上長: {mgr.display_name}"
        a(head)
        teams: dict[str, list[RosterEntry]] = defaultdict(list)
        for m in members:
            teams[m.team or "（チーム不明）"].append(m)
        for team, tm in sorted(teams.items(), key=lambda kv: -len(kv[1])):
            names = "、".join(m.display_name for m in tm[:8])
            more = f" ほか{len(tm) - 8}名" if len(tm) > 8 else ""
            a(f"    {team}（{len(tm)}名）  {names}{more}")
        a("")

    flagged = [e for e in review.entries if e.flags]
    if flagged:
        a("確認していただきたい人")
        for e in flagged[:20]:
            a(f"    {e.display_name:20s} {'、'.join(e.flags)}")
        if len(flagged) > 20:
            a(f"    ほか{len(flagged) - 20}名")
        a("")

    a(f"合計 {len(review.entries)}名")
    if review.headcount:
        miss = review.missing or 0
        if miss > 0:
            a(f"伺っていた従業員数は{review.headcount}名なので、**{miss}名が見つかっていません**。")
            a("どの部署の方が抜けているか分かれば教えてください。その方を起点に追加で収集します。")
        else:
            a(f"伺っていた従業員数（{review.headcount}名）とほぼ一致しています。")
    else:
        a("この中に抜けている方や、所属が違う方はいますか？")
    return "\n".join(out)


def split_batches(emails: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    uniq = sorted({e.strip().lower() for e in emails if e and e.strip()})
    return [uniq[i : i + size] for i in range(0, len(uniq), size)]


def write_batches(
    emails: list[str], workroot: Path, size: int = BATCH_SIZE
) -> list[dict[str, Any]]:
    """並列収集用に、バッチごとの専用ディレクトリと対象リストを用意する。

    実測では、複数エージェントが同じ作業ディレクトリに一時ファイルを書いて
    互いに上書きする事故が起きた。ディレクトリを分けるのは仕様であって、
    エージェントの裁量に任せる部分ではない。
    """
    batches = split_batches(emails, size)
    out: list[dict[str, Any]] = []
    for i, members in enumerate(batches):
        name = f"batch_{i + 1:02d}"
        d = workroot / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "targets.txt").write_text("\n".join(members) + "\n", encoding="utf-8")
        out.append(
            {
                "batch": name,
                "workdir": str(d),
                "targets_file": str(d / "targets.txt"),
                "output_file": str(d / "out.jsonl"),
                "count": len(members),
            }
        )
    return out


# ---------------------------------------------------------------- 波状収集

@dataclass
class Wave:
    """収集の1巡。新しく見つかった人は次の波で回収する。

    収集中に新しい人が見つかるのは正常。サブエージェントにその場で追いかけさせると、
    担当の重複・無限展開・集計の崩壊が起きる。**発見の記録だけして、親が次の波で回収する。**
    """

    observed: list[str]
    already_read: list[str]
    unread: list[str]
    newly_discovered: list[str]
    external_skipped: int = 0

    @property
    def converged(self) -> bool:
        return not self.unread

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed": len(self.observed),
            "already_read": len(self.already_read),
            "unread": len(self.unread),
            "newly_discovered": len(self.newly_discovered),
            "converged": self.converged,
            "targets": self.unread,
        }


def plan_wave(
    interactions: list[Interaction],
    already_read: list[str],
    previous_observed: int | None = None,
) -> tuple[Wave, list[str]]:
    """次の波の対象を決める。警告も返す。

    対象は「会議に現れたが、まだカレンダーを読んでいない人」。
    外部ドメインは対象にしない（社員ではない）。
    """
    read = {c.strip().lower() for c in already_read if c.strip()}
    observed: set[str] = set()
    external = 0
    for ev in interactions:
        for pid in ev.attendees:
            if pid.startswith("ext:"):
                external += 1
            else:
                observed.add(pid.lower())

    unread = sorted(observed - read)
    newly = sorted(observed - read) if previous_observed is None else unread

    warnings: list[str] = []
    if read and len(unread) > len(read) * 5:
        warnings.append(
            f"未読が {len(unread)} 名と、読んだ {len(read)} 名に対して不自然に多いです。"
            "顧客ドメインやメーリングリストを社内と誤判定すると、こうなります。"
            "`relana roster` で一覧を確認してください。"
        )
    if previous_observed is not None and len(observed) <= previous_observed:
        warnings.append("新しい人は見つかりませんでした。収束しています。")

    return (
        Wave(
            observed=sorted(observed),
            already_read=sorted(read),
            unread=unread,
            newly_discovered=newly,
            external_skipped=external,
        ),
        warnings,
    )

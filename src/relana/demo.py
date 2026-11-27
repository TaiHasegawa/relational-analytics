"""合成データ生成（FR-12.4 / `relana demo`）。

自社データなしで全機能を試せるようにする。
検証のため、既知の構造を意図的に埋め込んでいる（下記 GROUND_TRUTH）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .models import Person

DOMAIN = "example.co.jp"
SUPPLIER = "pkg-vendor.example.com"
CLIENT = "client.example.net"

GROUND_TRUTH = {
    "silo": "運営本部 — 部門間の会議をほぼ持たない（I/E 比が突出するはず）",
    "albind": "u_001 田中 — 製品開発/営業/運営を繋ぎ、外部サプライヤーへの唯一の接点",
    "efficiency_team": "QA — 内部密度が高く外部範囲も広い",
    "innovation_team": "ARCH — 内部密度が低く外部範囲が広い",
    "closed_team": "経理 — 内部は密だが外部との接点が乏しい",
    "isolated": "u_097 — 1on1 を一度も持たない",
}


@dataclass
class _Team:
    dept: str
    team: str
    size: int
    profile: str  # standard | efficiency | innovation | closed | silo


_LAYOUT = [
    _Team("製品開発本部", "パッケージング", 8, "standard"),
    _Team("製品開発本部", "コア", 10, "standard"),
    _Team("製品開発本部", "QA", 6, "efficiency"),
    _Team("製品開発本部", "アーキテクチャ", 6, "innovation"),
    _Team("営業本部", "東日本", 12, "standard"),
    _Team("営業本部", "西日本", 13, "standard"),
    _Team("マーケティング本部", "PR", 7, "standard"),
    _Team("マーケティング本部", "デジタル", 8, "standard"),
    _Team("運営本部", "サポート", 10, "silo"),
    _Team("運営本部", "業務", 8, "silo"),
    _Team("管理本部", "人事", 6, "standard"),
    _Team("管理本部", "経理", 6, "closed"),
]

_SURNAMES = (
    "田中 佐藤 鈴木 高橋 伊藤 渡辺 山本 中村 小林 加藤 吉田 山田 佐々木 山口 松本 "
    "井上 木村 林 斎藤 清水 山崎 森 池田 橋本 阿部 石川 山下 中島 石井 小川"
).split()


def build_persons() -> tuple[list[Person], dict]:
    persons: list[Person] = []
    meta: dict = {"teams": {}, "managers": {}}
    idx = 1
    for t in _LAYOUT:
        members = []
        for i in range(t.size):
            pid = f"u_{idx:03d}"
            name = f"{_SURNAMES[(idx - 1) % len(_SURNAMES)]}{idx:03d}"
            persons.append(
                Person(
                    person_id=pid,
                    email=f"user{idx:03d}@{DOMAIN}",
                    display_name=name,
                    dept=t.dept,
                    team=t.team,
                    role="マネジャー" if i == 0 else "メンバー",
                    hired_at=date(2015, 1, 1) + timedelta(days=idx * 37),
                    consent_status="consented",
                )
            )
            members.append(pid)
            idx += 1
        meta["teams"][t.team] = {"dept": t.dept, "members": members, "profile": t.profile}
        meta["managers"][t.team] = members[0]
    return persons, meta


def _label(pid: str) -> str:
    return pid


def generate(window_days: int = 90, seed: int = 42) -> tuple[list[dict], list[Person], dict]:
    rng = random.Random(seed)
    persons, meta = build_persons()
    by_id = {p.person_id: p for p in persons}
    end = datetime(2026, 3, 31, tzinfo=timezone.utc)
    start = end - timedelta(days=window_days)

    events: list[dict] = []
    counter = [0]

    def emit(
        attendees: list[str],
        when: datetime,
        duration: int,
        recurring: bool,
        uid: str,
        organizer: str,
        title: str | None = None,
        externals: list[str] | None = None,
        add_room: bool = False,
        declined: list[str] | None = None,
    ) -> None:
        counter[0] += 1
        att = []
        for pid in attendees:
            status = "accepted"
            if (declined and pid in declined) or rng.random() < 0.06:
                status = "declined"
            elif rng.random() < 0.12:
                status = "needsAction"
            elif rng.random() < 0.05:
                status = "tentative"
            att.append({"email": by_id[pid].email, "responseStatus": status})
        for ext in externals or []:
            att.append({"email": ext, "responseStatus": "accepted"})
        if add_room:
            att.append(
                {
                    "email": f"room{rng.randint(1, 6)}@resource.calendar.google.com",
                    "responseStatus": "accepted",
                    "resource": True,
                }
            )
        base = {
            "id": f"evt_{counter[0]:06d}",
            **({"summary": title} if title else {}),
            "iCalUID": uid,
            "start": {"dateTime": when.isoformat()},
            "end": {"dateTime": (when + timedelta(minutes=duration)).isoformat()},
            "organizer": {"email": by_id[organizer].email},
            "attendees": att,
        }
        if recurring:
            base["recurringEventId"] = uid
        # 同じ会議が参加者それぞれのカレンダーから取得される（R8 の重複排除を検証する）
        for _ in range(min(len(attendees), 3)):
            events.append(dict(base, id=f"evt_{counter[0]:06d}_{_}"))

    def weekdays(step_days: int, offset: int = 0):
        d = start + timedelta(days=offset)
        while d.weekday() >= 5:  # 週末開始だと step=7 で一件も生成されない
            d += timedelta(days=1)
        while d < end:
            yield d
            d += timedelta(days=step_days)

    teams = meta["teams"]

    # --- 1on1（マネジャー - メンバー、週次30分）
    for team, info in teams.items():
        mgr = info["members"][0]
        for member in info["members"][1:]:
            if member == "u_097":  # 孤立者: 1on1 を持たない
                continue
            if info["profile"] == "innovation" and rng.random() < 0.7:
                continue  # 内部の結び付きを緩くする
            for i, d in enumerate(weekdays(7, offset=rng.randint(0, 4))):
                emit([mgr, member], d.replace(hour=10), 30, True, f"1on1_{mgr}_{member}", mgr,
                     title=f"1on1 {_label(mgr)}/{_label(member)}")

    # --- チーム定例（週次30分）
    for team, info in teams.items():
        members = info["members"]
        for d in weekdays(7, offset=1):
            emit(members, d.replace(hour=9), 30, True, f"standing_{team}", members[0],
                 add_room=True, title=f"{team} 週次定例")

    # --- 効率型チーム: メンバー間のペア作業（内部密度を上げる）
    for team, info in teams.items():
        if info["profile"] not in ("efficiency", "closed"):
            continue
        members = info["members"]
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                for d in weekdays(21, offset=a + b):
                    emit([members[a], members[b]], d.replace(hour=13), 60, False,
                         f"pair_{team}_{a}_{b}_{d.date()}", members[a],
                         title=f"{team} ペア作業")

    # --- 部門定例（隔週60分・大人数）
    depts: dict[str, list[str]] = {}
    for info in teams.values():
        depts.setdefault(info["dept"], []).extend(info["members"])
    for dept, members in depts.items():
        for d in weekdays(14, offset=2):
            emit(members, d.replace(hour=16), 60, True, f"dept_{dept}", members[0],
                 add_room=True, title=f"{dept} 部門会議")

    # --- 部門マネジャー定例（部門推定の主要な手がかり）
    for dept, dept_teams in {
        d: [t for t, i in teams.items() if i["dept"] == d] for d in depts
    }.items():
        mgrs = [teams[t]["members"][0] for t in dept_teams]
        if len(mgrs) < 2:
            continue
        for d in weekdays(7, offset=4):
            emit(mgrs, d.replace(hour=8, minute=30), 30, True, f"mgr_{dept}", mgrs[0],
                 title=f"{dept} マネジャー定例")

    # --- 全社朝会（月次・100名）→ 重み関数により実質ゼロになるはず
    everyone = [p.person_id for p in persons]
    for d in weekdays(30, offset=3):
        emit(everyone, d.replace(hour=9, minute=30), 30, True, "allhands", everyone[0],
             title="全社朝会")

    # --- 部門横断プロジェクト（プロファイル別に接続の濃さを変える）
    # 継続するプロジェクトシリーズの本数
    cross_budget = {
        "standard": 3,
        "efficiency": 5,
        "innovation": 8,
        "closed": 0,   # 経理: 外部接点を持たない（閉鎖型）
        "silo": 0,     # 運営本部: 部門間の会議を持たない
    }
    # サイロ／閉鎖型のチームは、他チームからも相手に選ばれない
    isolated_members = {
        pid
        for i in teams.values()
        if i["profile"] in ("silo", "closed")
        for pid in i["members"]
    }
    all_days = list(weekdays(1))
    for team, info in teams.items():
        others = [
            pid
            for t2, i2 in teams.items()
            if i2["dept"] != info["dept"]
            for pid in i2["members"]
            if pid not in isolated_members
        ]
        n_meetings = cross_budget[info["profile"]]
        for _ in range(n_meetings):
            host = rng.choice(info["members"])
            if info["profile"] == "innovation":
                # 外部範囲を広く・重複しないように、メンバーごとに別の相手と繋ぐ
                host = info["members"][_ % len(info["members"])]
                partners = rng.sample(others, 3)
            elif info["profile"] == "efficiency":
                partners = rng.sample(others, 3)
            else:
                partners = rng.sample(others, 2)
            # プロジェクトは継続する。単発1回の会議は関係の証拠として弱く、
            # 閾値で落ちるのが設計上の正しい挙動（設計 §6.3）
            for d in weekdays(14, offset=rng.randint(0, 4)):
                emit(
                    [host, *partners],
                    d.replace(hour=rng.choice([11, 13, 14, 15])),
                    60,
                    True,
                    f"proj_{team}_{_}",
                    host,
                    add_room=rng.random() < 0.5,
                    title=f"PJ {team}-{_ + 1} 定例",
                )

    # --- イノベーションチームは内部の定例を間引く（内部密度を下げる）
    events[:] = [
        e
        for e in events
        if not (e["iCalUID"] == "standing_アーキテクチャ" and rng.random() < 0.6)
    ]

    # --- アルビンド（u_001）: 部門を跨ぐ橋渡し＋外部サプライヤーへの唯一の接点
    albind = "u_001"
    # 運営本部はサイロとして隔離したいので橋渡し先に含めない
    bridge_targets = (
        teams["東日本"]["members"][:3]
        + teams["西日本"]["members"][:2]
        + teams["PR"]["members"][:2]
        + teams["人事"]["members"][:2]
    )
    for target in bridge_targets:
        for d in weekdays(14, offset=5):
            emit([albind, target], d.replace(hour=11), 30, True, f"bridge_{target}", albind,
                 title="パッケージ調整")
    for d in weekdays(7, offset=6):
        emit([albind], d.replace(hour=17), 60, True, "supplier", albind,
             externals=[f"sales@{SUPPLIER}"], title="サプライヤー定例")

    # --- 営業の外部顧客ミーティング
    for pid in teams["東日本"]["members"][:5] + teams["西日本"]["members"][:5]:
        for d in weekdays(14, offset=rng.randint(0, 4)):
            emit([pid], d.replace(hour=14), 60, True, f"client_{pid}", pid,
                 externals=[f"contact@{CLIENT}"], title="顧客定例")

    # --- ノイズ: 終日イベント（休暇）
    for pid in rng.sample(everyone, 20):
        d = rng.choice(all_days)
        counter[0] += 1
        events.append(
            {
                "id": f"evt_{counter[0]:06d}",
                "iCalUID": f"holiday_{pid}",
                "start": {"date": d.date().isoformat()},
                "end": {"date": (d + timedelta(days=1)).date().isoformat()},
                "organizer": {"email": by_id[pid].email},
                "attendees": [{"email": by_id[pid].email, "responseStatus": "accepted"}],
            }
        )

    rng.shuffle(events)
    return events, persons, meta

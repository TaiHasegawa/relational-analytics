"""指標を組み合わせて「役割」にする。

人事部長は「制約スコア 0.11」では動けない。「この人は橋渡し役で、抜けると接点が切れる」
なら動ける。**新しい指標は作らず、既存の6指標の組み合わせだけで判定する。**

役職は使わない。我々が持っているのは1on1の星形から推定した「マネジャーらしき人」
だけであり、部長・課長・主任の区別は推定できない。推定値を基準にした役割は
根拠が二重に弱くなるため作らない。
"""

from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any

import networkx as nx

from ..models import Interaction


@dataclass
class RoleConfig:
    """役割の判定に使う閾値。レポートに記録して、後から確認できるようにする。"""

    broker_min_depts: int = 2          # 橋渡し役: 接する他部門の数
    broker_min_openness_pct: float = 70.0  # 橋渡し役: 制約の低さ（部門内パーセンタイル）
    conduit_min_betweenness: float = 0.01  # 情報の通り道: 他の人どうしの経路が通る割合
    load_min_pct: float = 80.0         # 負荷が集中: 会議時間の部門内順位
    internal_min_brokerage: int = 5    # 部門内のまとめ役: 部門内の仲介回数
    internal_max_depts: int = 1        # 部門内のまとめ役: 接する他部門の数の上限
    thin_max_degree_pct: float = 10.0  # 接点が少ない人: 同席相手の数の部門内順位
    thin_no_dyad_degree_pct: float = 25.0  # 1on1 が無い場合に、追加で満たすべき順位


@dataclass
class Role:
    key: str
    label: str
    why: str
    actions: list[str] = field(default_factory=list)


@dataclass
class PersonRoles:
    person_id: str
    label: str
    dept: str
    roles: list[Role]

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "label": self.label,
            "dept": self.dept,
            "roles": [asdict(r) for r in self.roles],
            "role_keys": [r.key for r in self.roles],
        }


def brokerage_counts(
    g: nx.Graph, group_attr: str = "dept"
) -> dict[str, Counter]:
    """仲介の種類を数える（Gould & Fernandez の無向版）。

    直接つながっていない2人の間に立っているとき、3者の所属で分類する。
    主催者を使わないため方向が取れず、「外から内へ」と「内から外へ」は区別しない。
    """
    out: dict[str, Counter] = defaultdict(Counter)
    for v, data in g.nodes(data=True):
        if data.get("is_external"):
            continue
        dv = data.get(group_attr)
        nbrs = [x for x in g.neighbors(v) if not g.nodes[x].get("is_external")]
        for a, c in combinations(nbrs, 2):
            if g.has_edge(a, c):
                continue
            da = g.nodes[a].get(group_attr)
            dc = g.nodes[c].get(group_attr)
            if da == dc == dv:
                out[v]["internal"] += 1
            elif da == dv or dc == dv:
                out[v]["cross"] += 1
            else:
                out[v]["other"] += 1
    return out


def meeting_minutes(interactions: list[Interaction]) -> dict[str, float]:
    load: dict[str, float] = defaultdict(float)
    for ev in interactions:
        for pid in ev.attendees:
            if not pid.startswith("ext:"):
                load[pid] += ev.duration_min or 0
    return dict(load)


def assign(
    snap,
    bundle,
    interactions: list[Interaction],
    cfg: RoleConfig | None = None,
    group_attr: str = "dept",
) -> dict[str, PersonRoles]:
    cfg = cfg or RoleConfig()
    g = bundle.undirected
    internal = [n for n, a in g.nodes(data=True) if not a.get("is_external")]
    if not internal:
        return {}

    by_person: dict[str, dict[str, Any]] = defaultdict(dict)
    for f in snap.findings:
        if f.level == "person":
            by_person[f.entity_id][f.metric] = f
    vuln = {f.entity_id: f for f in snap.findings if f.feature == "vulnerability"}

    brok = brokerage_counts(g, group_attr)
    load = meeting_minutes(interactions)
    degree = {n: g.degree(n) for n in internal}
    dyads = {n: bundle.one_on_one.degree(n) for n in internal}
    dept_of = {n: g.nodes[n].get(group_attr) or "(未設定)" for n in internal}
    cross_depts = {
        n: len(
            {
                dept_of[x]
                for x in g.neighbors(n)
                if x in dept_of and dept_of[x] != dept_of[n]
            }
        )
        for n in internal
    }

    def pct(values: dict[str, float], n: str) -> float:
        """部門内でのパーセンタイル。比較できる集団の中でだけ順位を付ける。"""
        peers = [values.get(m, 0.0) for m in internal if dept_of[m] == dept_of[n]]
        if len(peers) < 2:
            return 50.0
        below = sum(1 for v in peers if v < values.get(n, 0.0))
        return 100.0 * below / (len(peers) - 1)

    # 「直接の相手が少ない」の基準。全社の中央値を使う
    _direct = [
        f.extra.get("direct_contacts")
        for f in (by_person[m].get("betweenness") for m in internal)
        if f is not None and f.extra.get("direct_contacts") is not None
    ]
    median_direct = st.median(_direct) if _direct else 0.0

    out: dict[str, PersonRoles] = {}
    for n in internal:
        label = g.nodes[n].get("display_name") or n
        inf = by_person[n].get("betweenness")
        con = by_person[n].get("constraint")
        roles: list[Role] = []

        openness = con.percentile if con else None  # 高いほど制約が低い
        if cross_depts[n] >= cfg.broker_min_depts and (openness or 0) >= cfg.broker_min_openness_pct:
            roles.append(Role(
                "broker", "橋渡し役",
                f"{cross_depts[n]}部門と接点があり、つながっている相手どうしがつながっていない"
                f"（相手が別々の集団に散っている順に、部門内で上位{100 - (openness or 0):.0f}%）",
                ["部門をまたぐプロジェクトに参加させる",
                 "異動させる場合は、同席している部門との接点を先に別の人へ移す"],
            ))

        # 順位ではなく実際の値で判定する。順位だと、経路がほとんど通らない人でも
        # 直接の相手がそれ以上に少なければ「通り道」に出てしまう。
        conduit = (
            inf is not None
            and (inf.value or 0) >= cfg.conduit_min_betweenness
            and (inf.extra.get("direct_contacts") or 0) <= median_direct
        )
        if conduit:
            roles.append(Role(
                "conduit", "情報の通り道になっている人",
                f"直接会ったのは{inf.extra['direct_contacts']}名"
                f"（全社の中央値は{median_direct:.0f}名）だが、"
                f"他の人どうしの経路の{inf.value:.1%} が {label} を通る",
                [f"新しい方針を周知するとき、{label} に最初に説明する"],
            ))

        if n in vuln:
            f = vuln[n]
            roles.append(Role(
                "single_point", "抜けると接点が切れる人",
                f.interprets_as,
                f.suggested_actions,
            ))

        if pct(load, n) >= cfg.load_min_pct and (n in vuln or conduit):
            hours = load.get(n, 0) / 60
            roles.append(Role(
                "overloaded", "負荷が集中している人",
                f"会議時間が{hours:.0f}時間で、部門内の上位{100 - pct(load, n):.0f}%にあたる。"
                "組織にとって重要な位置にいる",
                [f"{label} が出ている定期会議のうち、別の人が代われるものがないか確認する",
                 f"{label} を通さずに進められる仕事がないか確認する"],
            ))

        if brok[n]["internal"] >= cfg.internal_min_brokerage and cross_depts[n] <= cfg.internal_max_depts:
            roles.append(Role(
                "internal_hub", "部門内のまとめ役",
                f"部門内で{brok[n]['internal']}組を仲介しているが、"
                f"他部門との接点は{cross_depts[n]}部門",
                [f"{label} に部門外との接点を持たせると、部門全体の情報の入口が増える"],
            ))

        if dyads[n] == 0 and pct(degree, n) <= cfg.thin_no_dyad_degree_pct:
            roles.append(Role(
                "thin", "接点が少ない人",
                f"1on1 がなく、つながっている相手は{degree[n]}名",
                ["本人または上長に、会議以外で接点があるかを確認する"],
            ))
        elif pct(degree, n) <= cfg.thin_max_degree_pct:
            roles.append(Role(
                "thin", "接点が少ない人",
                f"つながっている相手が{degree[n]}名で、部門内の下位{pct(degree, n):.0f}%にあたる",
                ["本人または上長に、会議以外で接点があるかを確認する"],
            ))

        if roles:
            out[n] = PersonRoles(
                person_id=n,
                label=label,
                dept=dept_of[n],
                roles=roles,
            )
    return out


def priority(people: dict[str, PersonRoles], limit: int = 8) -> list[PersonRoles]:
    """複数の役割を持つ人を上に出す。優先順位は指標をまたぐため、ここで横断して決める。"""
    weight = {"single_point": 3, "overloaded": 2, "broker": 2, "conduit": 1,
              "internal_hub": 1, "thin": 1}
    scored = sorted(
        people.values(),
        key=lambda p: (-sum(weight.get(r.key, 1) for r in p.roles), -len(p.roles), p.person_id),
    )
    return [p for p in scored if len(p.roles) >= 2][:limit]


def missing_roles(people: dict[str, PersonRoles], g: nx.Graph, group_attr: str = "dept") -> list[dict]:
    """部門ごとに、いない役割を出す。個人ではなく組織の設計の問題として示す。"""
    members: dict[str, list[str]] = defaultdict(list)
    for n, a in g.nodes(data=True):
        if not a.get("is_external"):
            members[a.get(group_attr) or "(未設定)"].append(n)
    out = []
    for dept, mem in sorted(members.items(), key=lambda kv: -len(kv[1])):
        have = Counter()
        for m in mem:
            for r in people.get(m, PersonRoles(m, m, dept, [])).roles:
                have[r.key] += 1
        out.append({
            "dept": dept,
            "size": len(mem),
            "brokers": have["broker"],
            "conduit": have["conduit"],
            "single_points": have["single_point"],
            "thin": have["thin"],
            "action": (
                "他部門との接点を持つ人がいません。他部門との合同会議を設定してください。"
                if have["broker"] == 0 else ""
            ),
        })
    return out

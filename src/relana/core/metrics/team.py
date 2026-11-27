"""❸効率性 / ❹イノベーション — 内部密度 x 外部範囲（典拠: 第5章 p.104-108）。

同じ2変数を逆向きに使う。
  効率性       内部密度 高 x 外部範囲 広  -> 納期を守れる
  イノベーション 内部密度 低 x 外部範囲 広  -> 創造的摩擦が生まれる

「効率性の特徴を持つチームは、イノベーション集団としては失敗する可能性が最も高い」
"""

from __future__ import annotations

import statistics
from itertools import combinations

import networkx as nx

from .base import CALENDAR_CAVEAT, Finding, group_members

SOURCE = "第5章 p.104-108（図表5-3 / 5-4）"


def compute(g: nx.Graph, team_attr: str = "team", min_size: int = 3) -> list[Finding]:
    teams = {k: v for k, v in group_members(g, team_attr).items() if len(v) >= min_size}
    if not teams:
        return []

    raw: dict[str, dict[str, float]] = {}
    for name, members in teams.items():
        raw[name] = _team_metrics(g, members)

    densities = [m["internal_density"] for m in raw.values()]
    ranges = [m["external_range"] for m in raw.values()]
    med_d = statistics.median(densities)
    med_r = statistics.median(ranges)
    med_nr = statistics.median([m["external_nonredundancy"] for m in raw.values()])
    med_reach = statistics.median([m["external_reach"] for m in raw.values()])

    findings: list[Finding] = []
    for name, m in raw.items():
        quadrant, label, meaning = _quadrant(m["internal_density"], m["external_range"], med_d, med_r)
        d_dev = m["internal_density"] / med_d if med_d else 1.0
        r_dev = m["external_range"] / med_r if med_r else 1.0
        reading = _reading(quadrant, d_dev, r_dev, m["external_nonredundancy"], med_nr)
        if reading == "typical":
            label = "中央値付近"
            meaning = "メンバーどうしのつながりも、部門外との接点の広さも、全部門の中央値に近い"
        elif reading == "diffuse_overlap":
            label = "外部接点が重なっている型"
            meaning = "メンバーが部門外の同じ相手と会っている"
        elif reading == "diffuse_narrow":
            label = "外部接点が少ない型"
            meaning = "部門外でつながっている相手が、1人あたりで見て少ない"
        findings.append(
            Finding(
                feature="team",
                level="team",
                metric="density_x_range",
                entity_id=name,
                entity_label=name,
                value=round(m["internal_density"], 4),
                direction="neutral",
                status="ok",
                comparison_group="全部門",
                comparison_n=len(teams),
                source=SOURCE,
                interprets_as=meaning,
                does_not_mean="この分類は部門の優劣を表さない。納期を守る仕事と新規探索の仕事では、望ましい型が逆になる",
                caveats=[
                    CALENDAR_CAVEAT,
                    "効率性の特徴を持つ部門は、イノベーション集団としては失敗する可能性が最も高い",
                    f"全{len(teams)}部門の中央値で4つに分けた。中央値付近の部門は、わずかな差で別の型に移る",
                ],
                suggested_actions=_actions(reading),
                extra={
                    "quadrant": quadrant,
                    "quadrant_label": label,
                    "reading": reading,
                    "density_vs_median": round(d_dev, 2),
                    "range_vs_median": round(r_dev, 2),
                    "median_external_nonredundancy": round(med_nr, 3),
                    "median_external_reach": round(med_reach, 2),
                    "internal_density": round(m["internal_density"], 4),
                    "classic_density": round(m["classic_density"], 4),
                    "external_range": round(m["external_range"], 4),
                    "external_reach": round(m["external_reach"], 2),
                    # 「1人あたり 0.10 名」は思い浮かべられない。実際の人数も持たせる
                    "external_alters": int(round(m["external_reach"] * m["size"])),
                    "typical_external_alters": int(round(med_reach * m["size"])),
                    # 重複のぐあいは「同じ相手に何名が会っているか」で書くと伝わる
                    "members_per_alter": round(1 / m["external_nonredundancy"], 1)
                    if m["external_nonredundancy"]
                    else None,
                    "median_members_per_alter": round(1 / med_nr, 1) if med_nr else None,
                    "external_nonredundancy": round(m["external_nonredundancy"], 3),
                    "size": m["size"],
                    "median_internal_density": round(med_d, 4),
                    "median_external_range": round(med_r, 4),
                },
            )
        )
    return findings


def _team_metrics(g: nx.Graph, members: list[str]) -> dict[str, float]:
    m = len(members)
    mset = set(members)

    # 内部密度: 1人あたりの部門内接触量（平均重み付き次数）。
    # 単純な「総重み / 可能ペア数」はペア数が n^2 で増えるため小部門が機械的に有利になる。
    # 1人あたりに正規化することで規模バイアスを除く。
    possible = m * (m - 1) / 2
    internal_w = sum(
        g[a][b].get("weight", 1.0) for a, b in combinations(members, 2) if g.has_edge(a, b)
    )
    internal_density = 2.0 * internal_w / m if m else 0.0
    classic_density = internal_w / possible if possible else 0.0

    # 外部範囲: 部門外アルターの広さ x 非重複度
    per_member: list[set[str]] = []
    for node in members:
        alters = {nb for nb in g.neighbors(node) if nb not in mset}
        per_member.append(alters)
    union = set().union(*per_member) if per_member else set()
    total_individual = sum(len(s) for s in per_member)
    nonredundancy = len(union) / total_individual if total_individual else 0.0
    reach = len(union) / m if m else 0.0
    external_range = reach * nonredundancy

    return {
        "size": m,
        "internal_density": internal_density,
        "classic_density": classic_density,
        "external_reach": reach,
        "external_nonredundancy": nonredundancy,
        "external_range": external_range,
    }


def _quadrant(d: float, r: float, med_d: float, med_r: float) -> tuple[str, str, str]:
    high_d, high_r = d >= med_d, r >= med_r
    if high_d and high_r:
        return (
            "efficiency",
            "効率型",
            "メンバーどうしのつながりが濃く、部門外にも重複しない接点がある",
        )
    if not high_d and high_r:
        return (
            "innovation",
            "イノベーション型",
            "メンバーどうしのつながりが薄く、部門外に重複しない接点がある",
        )
    if high_d and not high_r:
        return (
            "closed",
            "閉鎖型",
            "メンバーどうしのつながりは濃いが、部門外とのつながりが少ない",
        )
    return (
        "diffuse",
        "拡散型",
        "メンバーどうしのつながりも、部門外とのつながりも少ない",
    )


# 中央値からこの割合の中に入るときは、型による差が出ていないとみなす
NEAR_MEDIAN = 0.2


def _reading(quadrant: str, d_dev: float, r_dev: float, nonred: float, med_nr: float) -> str:
    """象限だけでは打ち手が決まらないので、中央値からの離れ方で読み方を分ける。

    2つの軸はどちらも中央値で切っている。中央値のすぐ近くにいる部門は、
    わずかな差で別の型に移るため、型の名前から打ち手を決めると根拠にならない。

    左下の象限（内部密度も外部範囲も中央値未満）は、原因が2つに分かれる。
    部門外の相手そのものが少ない場合と、メンバーが同じ相手と会っていて
    重複している場合で、やることが逆になる。重複しない割合で見分ける。
    """
    if abs(d_dev - 1.0) <= NEAR_MEDIAN and abs(r_dev - 1.0) <= NEAR_MEDIAN:
        return "typical"
    if quadrant == "diffuse":
        return "diffuse_overlap" if nonred < med_nr else "diffuse_narrow"
    return quadrant


def _actions(reading: str) -> list[str]:
    return {
        "efficiency": ["納期を守る必要があるプロジェクトを任せる", "新規探索を任せる場合は、メンバーを入れ替えて顔ぶれの偏りを減らす"],
        "innovation": ["新規探索や新商品開発を任せる", "納期が厳しい案件では、着手前にメンバー間で段取りを確認させる"],
        "closed": ["他部門と接点のあるメンバーを加える", "部門外の担当者を部門の会議に呼ぶ"],
        "diffuse_narrow": [
            "他部門の定例に、この部門から1人を継続して参加させる",
            "部門外の担当者を部門の会議に呼ぶ",
        ],
        "diffuse_overlap": [
            "部門外との窓口をメンバーで分担し、同じ相手に複数人が出ている会議を1人に絞る",
            "空いた時間を、まだつながっていない相手との接点に充てる",
        ],
        "typical": [],
    }.get(reading, [])

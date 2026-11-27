"""❺ サイロ — モジュール性（典拠: 第5章 p.108-111）。

典拠は、内部と外部のコミュニケーション比率が 5:1 を超えたらサイロ化していると評価する。
書籍の事例では運営部門が 13:1 だった。

ただし **I/E 比は部門の人数に左右される**。100名の会社で誰とでも等しく会う人を考えると、
12名の部門なら I/E = 11/88 = 0.125、30名の部門なら 29/70 = 0.414 になる。
**何もしなくても大きい部門のほうが3倍高く出る。**

そこで「ランダムに会っていた場合の何倍か」を併せて出す。
合成データでは、管理本部（12名・I/E 3.67）がランダムの29.4倍で、
製品開発本部（30名・I/E 1.53、3.7倍）の8倍サイロ化していた。
絶対値の閾値 5.0 だけでは、この管理本部を「問題なし」と判定してしまう。
"""

from __future__ import annotations

from itertools import combinations

import networkx as nx

from .base import CALENDAR_CAVEAT, Finding, group_members

SOURCE = "第5章 p.108-111（図表5-5）"


def compute(
    g: nx.Graph,
    group_attr: str = "dept",
    threshold: float = 5.0,
    groups_inferred: bool = False,
) -> list[Finding]:
    groups = group_members(g, group_attr)
    if len(groups) < 2:
        return []

    internal_w: dict[str, float] = {k: 0.0 for k in groups}
    external_w: dict[str, float] = {k: 0.0 for k in groups}
    cross: dict[tuple[str, str], float] = {}
    member_of = {n: k for k, members in groups.items() for n in members}

    for a, b, data in g.edges(data=True):
        ga, gb = member_of.get(a), member_of.get(b)
        if ga is None or gb is None:
            continue  # 外部エンティティはサイロ判定の対象外
        w = data.get("weight", 1.0)
        if ga == gb:
            internal_w[ga] += w
        else:
            external_w[ga] += w
            external_w[gb] += w
            key = (ga, gb) if ga <= gb else (gb, ga)
            cross[key] = cross.get(key, 0.0) + w

    # 継続的な接点が残らなかった相手部門。打ち手をこの部門の状況に合わせるために使う。
    # 弱い記録（1回だけの大人数の会議など）は min_edge_weight で落としているので、
    # 「1件もない」とは書けない。
    names = sorted(groups)
    zero_contact = {
        k: [
            o
            for o in names
            if o != k and cross.get((k, o) if k <= o else (o, k), 0.0) <= 0.0
        ]
        for k in names
    }

    # いま接点が残っている相手。打ち手をその部門の状況に合わせるのに使う
    linked = {
        k: [
            o
            for o in names
            if o != k and cross.get((k, o) if k <= o else (o, k), 0.0) > 0.0
        ]
        for k in names
    }

    # ランダムに会う場合の期待値。n-1 人が部門内、N-n 人が部門外にいる
    total_people = sum(len(v) for v in groups.values())
    expected = {
        k: ((len(v) - 1) / (total_people - len(v)) if total_people > len(v) else float("inf"))
        for k, v in groups.items()
    }
    # 相対の閾値は、典拠の絶対閾値を「平均的な人数の部門」に当てはめて導く。
    # 典拠の 5:1 は、平均的な部門にとってランダムの何倍かを求める。
    avg_size = total_people / len(groups)
    exp_avg = (avg_size - 1) / (total_people - avg_size) if total_people > avg_size else 1.0
    rel_threshold = threshold / exp_avg if exp_avg > 0 else float("inf")

    inferred_caveat = (
        "部門はカレンダーから推定したものです。推定した区分で『区分間の往来が少ない』と測ると"
        "循環論法になりかねないため、この結果は下書きとして扱い、"
        "実際の組織図に合わせて persons.csv の dept 列を修正してから判断してください。"
    )

    findings: list[Finding] = []
    for name, members in groups.items():
        ext = external_w[name]
        ratio = internal_w[name] / ext if ext > 0 else float("inf")
        exp = expected[name]
        rel = ratio / exp if exp not in (0, float("inf")) and ratio != float("inf") else float("inf")
        status = _status(ratio, rel, threshold, rel_threshold)
        findings.append(
            Finding(
                feature="silo",
                level="org",
                metric="ie_ratio",
                entity_id=name,
                entity_label=name,
                value=round(ratio, 2) if ratio != float("inf") else None,
                direction="lower_is_better",
                threshold=threshold,
                status=status,
                comparison_group="全部門",
                comparison_n=len(groups),
                source=SOURCE,
                interprets_as=(
                    f"部門の中だけのつながりが、部門の外とのつながりの{ratio:.1f}倍ある。"
                    f"この人数（{len(members)}名）でランダムに会うなら{exp:.2f}倍になるので、"
                    f"その{rel:.1f}倍にあたる"
                    if ratio != float("inf")
                    else "この部門と他部門の間に、継続的と言える接点が残っていない"
                ),
                does_not_mean="この数値は部門の生産性を表さない。専門性の高い部門では、部門の中のつながりが増える",
                caveats=[
                    CALENDAR_CAVEAT,
                    f"この部門は{len(members)}名。部門によって会議を登録する習慣が違う場合、比率も変わる",
                    f"I/E 比は人数に左右される。全{total_people}名のうち{len(members)}名の部門なら、"
                    f"ランダムにつながっても{exp:.2f}倍になる",
                ]
                + ([inferred_caveat] if groups_inferred else []),
                suggested_actions=_actions(
                    status, ext == 0, zero_contact[name], linked[name]
                ),
                extra={
                    "internal_weight": round(internal_w[name], 3),
                    "external_weight": round(ext, 3),
                    "member_count": len(members),
                    "no_external_contact": ext == 0,
                    # 「3.67倍」は思い浮かべにくい。「79%が部門の中」に直して出す
                    "internal_share": round(_share(ratio), 3),
                    "expected_share": round(_share(exp), 3),
                    "threshold_share": round(_share(rel_threshold * exp), 3)
                    if exp not in (0, float("inf"))
                    else None,
                    "zero_contact_depts": zero_contact[name],
                    "display": "-" if ratio == float("inf") else f"{ratio:.2f}",
                    "expected_ie": round(exp, 3) if exp != float("inf") else None,
                    "times_random": round(rel, 1) if rel != float("inf") else None,
                    "times_random_display": "-" if rel == float("inf") else f"{rel:.1f}",
                    "relative_threshold": round(rel_threshold, 1),
                },
            )
        )

    findings.append(_matrix_finding(groups, internal_w, cross))
    findings.append(_modularity_finding(g, groups, member_of))
    findings.extend(_disconnected_pairs(groups, cross, member_of, g))
    return findings


def _share(ratio: float) -> float:
    """内外比を「同席のうち部門の中が占める割合」に直す。

    「部門外との会議の3.67倍」は頭の中で割り算が必要になる。
    同じことを「同席の79%が部門の中」と書くと、1回読んで分かる。
    """
    if ratio == float("inf"):
        return 1.0
    return ratio / (1.0 + ratio)


def _actions(
    status: str, no_external: bool, zero: list[str], linked: list[str]
) -> list[str]:
    """部門の状況ごとに打ち手を変える。

    継続的な接点がない部門があるかどうかで、やることが変わる。すべての部門に同じ
    「全部門のマネジャーが集まる会議を作る」を出すと、どこから手を付けるかが決まらない。

    接点が1〜2部門にしか残っていない場合は、残っている相手を名前で出す。
    接点がない部門の名前だけを並べると、閉じている部門どうしで打ち手が同じ文面になる。
    """
    if status == "ok":
        return []
    if no_external:
        return [
            f"接点が残っていない{len(zero)}部門のうち、業務上つながる必要がある部門を決める",
            "決めた部門との間に、双方の担当者が出る定例を1つ作る",
            "この部門が持っているデータや情報を一覧にし、他部門が使えるものがないか確認する",
        ]
    if zero and len(linked) <= 2:
        return [
            f"{'、'.join(linked)} 以外の{len(zero)}部門のうち、"
            "業務上つながる必要がある部門を決める",
            "決めた部門との間に、双方の担当者が出る定例を1つ作る",
            "この部門が持っているデータや情報を一覧にし、他部門が使えるものがないか確認する",
        ]
    if zero:
        head = "、".join(zero[:3])
        tail = f" ほか{len(zero) - 3}部門" if len(zero) > 3 else ""
        return [
            f"{head}{tail} との間に、双方の担当者が出る会議を作る",
            "この部門のマネジャーを、他部門の定例に1つ参加させる",
        ]
    return [
        "他部門が主体の会議に、この部門のメンバーを継続して参加させる",
        "この部門が持っているデータや情報を一覧にし、他部門が使えるものがないか確認する",
    ]


def _status(ratio: float, rel: float, threshold: float, rel_threshold: float) -> str:
    """絶対値と、人数で補正した相対値の両方で判定する。

    相対の閾値は典拠の絶対閾値から導いている。
    平均的な人数の部門にとって 5:1 がランダムの何倍かを求め、それを基準にする。
    """
    if ratio == float("inf") or rel == float("inf"):
        return "critical"
    if ratio > threshold * 2 or rel > rel_threshold * 2:
        return "critical"
    if ratio > threshold or rel > rel_threshold:
        return "warning"
    if rel > rel_threshold * 0.5:
        return "watch"
    return "ok"


def _matrix_finding(groups: dict, internal_w: dict, cross: dict) -> Finding:
    """部門ごとに同席した会議の量を集計した行列。ヒートマップで表示する。"""
    names = sorted(groups, key=lambda k: -len(groups[k]))
    matrix = []
    for a in names:
        row = []
        for b in names:
            if a == b:
                row.append(round(internal_w.get(a, 0.0), 3))
            else:
                key = (a, b) if a <= b else (b, a)
                row.append(round(cross.get(key, 0.0), 3))
        matrix.append(row)
    # 人数差を補正した「1ペアあたりの往来量」も出す
    normed = []
    for i, a in enumerate(names):
        row = []
        for j, b in enumerate(names):
            pairs = (
                len(groups[a]) * (len(groups[a]) - 1) / 2
                if a == b
                else len(groups[a]) * len(groups[b])
            )
            row.append(round(matrix[i][j] / pairs, 4) if pairs else 0.0)
        normed.append(row)
    return Finding(
        feature="silo",
        level="org",
        metric="dept_matrix",
        entity_id="__matrix__",
        entity_label="部門間の往来",
        value=None,
        direction="neutral",
        source=SOURCE,
        interprets_as="部門ごとのつながりの量。対角が部門内、それ以外が部門間",
        does_not_mean="つながりが多いほど良いとは言えない。業務上の関連がない部門間は、つながりがなくても支障はない",
        caveats=[CALENDAR_CAVEAT, "人数が多い部門は合計が大きくなるため、1ペアあたりの値も併記した"],
        extra={
            "labels": names,
            "sizes": [len(groups[n]) for n in names],
            "total": matrix,
            "per_pair": normed,
        },
    )


def _modularity_finding(g: nx.Graph, groups: dict, member_of: dict) -> Finding:
    communities = [set(v) for v in groups.values()]
    sub = g.subgraph(list(member_of))
    try:
        q = nx.community.modularity(sub, communities, weight="weight")
    except Exception:
        q = 0.0
    return Finding(
        feature="silo",
        level="org",
        metric="modularity_q",
        entity_id="__org__",
        entity_label="組織全体",
        value=round(q, 4),
        direction="lower_is_better",
        status="warning" if q > 0.6 else "ok",
        source=SOURCE,
        interprets_as="部門の区分と、実際につながっている集団が一致する度合い。1に近いほど、部門をまたぐつながりが少ない",
        does_not_mean="この数値は組織設計の良し悪しを表さない。専門性を分けた組織では値が上がる",
        caveats=[CALENDAR_CAVEAT],
        extra={"n_groups": len(groups)},
    )


def _disconnected_pairs(
    groups: dict, cross: dict, member_of: dict, g: nx.Graph
) -> list[Finding]:
    """部門間の断絶ペアと、そこを繋いでいる数少ない人物を抽出する。"""
    out: list[Finding] = []
    names = sorted(groups)
    for a, b in combinations(names, 2):
        w = cross.get((a, b), 0.0)
        expected = len(groups[a]) * len(groups[b])
        bridges = [
            n
            for n in groups[a]
            if any(member_of.get(nb) == b for nb in g.neighbors(n))
        ]
        if w > 0 and len(bridges) > 2:
            continue
        out.append(
            Finding(
                feature="silo",
                level="org",
                metric="disconnected_pair",
                entity_id=f"{a}__{b}",
                entity_label=f"{a} ↔ {b}",
                value=round(w, 3),
                direction="higher_is_better",
                status="critical" if w == 0 else "warning",
                source=SOURCE,
                interprets_as=(
                    "この2部門の間に、継続的と言える接点が残っていない"
                    if w == 0
                    else f"この2部門をつないでいるのは{len(bridges)}名だけ"
                ),
                does_not_mean="接点がないこと自体は問題を表さない。業務上の関連がない部門間なら、接点がなくても支障はない",
                caveats=[CALENDAR_CAVEAT],
                extra={
                    "possible_pairs": expected,
                    "bridge_persons": bridges,
                },
            )
        )
    return out

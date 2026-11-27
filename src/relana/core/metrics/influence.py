"""❷ 影響力 — 集合的傑出性（典拠: 第5章 p.102-104）。

典拠は「最も多くの同僚から影響力があると評価される人物が、実際に最も影響力のある
人物とは限らない」とし、最も強力なインフルエンサーの特徴をこう書いている。

  1. たとえ少人数でも他者との間に強力なつながりを持つ
  2. その強い結び付きを通して、自身のコネクションと他者のコネクションを結び付ける
  → その結果、アイデアはより遠くまで広がる

この「自身のコネクションと他者のコネクションを結び付ける」位置を、**媒介中心性**で測る。
他の人どうしの最短経路がその人を通る割合であり、同席の重みを距離に直して重み付きで求める。

## 主催者を使わない理由

当初は主催者→参加者の有向グラフ上の PageRank を使っていた。合成データで測った結果、
主催するかどうかはマネジャーかどうかでほぼ決まっていた（r = +0.927。
マネジャー12名の主催量は中央値48.9、非マネジャー88名は中央値0.0）。
**組織図以上の情報を持たない。** 実務でも、アシスタントが代理で設定する、
定期会議は設定した人が主催者のまま残るなど、主催の記録は信頼できない。

## 到達人数を使わない理由

1人経由で何人に届くかを数える方法も試した。媒介中心性と同じ順位傾向を示し
（パーセンタイル相関 +0.517）、似た指標を2つ並べることになる。
「アイデアを他の集団へ渡す位置にいるか」を直接測るのは媒介中心性のほうで、
到達人数は同席数が多い人を上位に出しやすい。指標は媒介中心性に一本化した。

## 他の中心性を使わない理由（合成データで実測）

| 手法 | 接触数との順位相関 | 問題 |
|---|---|---|
| 無向 PageRank | +0.941 | ほぼ接触数と同じ。再帰性が消える |
| Katz 中心性 | +0.991 | 同上 |
| 固有ベクトル中心性 | +0.565 | 密なクリークに値が集中する（上位8名中5名が同一チーム） |
| **媒介中心性** | **+0.496** | 接触数と別のものを測っている |

媒介中心性は「ハブとなっている人」でも使う。あちらは媒介中心性が高い人のうち、
抜けると会議でつながらなくなる人がいるかを見る。こちらは全員の値を出し、
誰に最初に伝えるかを決めるのに使う。

## 順位（パーセンタイル）で選ばない理由

「直接の相手の順位より媒介中心性の順位が高い人」で選んでいた時期がある。
順位は人数で決まるため、合成データでは**他の人どうしの経路が 0.04% しか通らない人**が
上位に出た。その人を周知の相手に挙げても情報は広がらない。
選ぶのは実際の値（`MIN_BETWEENNESS`）と、直接の相手が全社の中央値以下かで行う。
"""

from __future__ import annotations

import statistics

import networkx as nx

from .base import CALENDAR_CAVEAT, Finding, distance_graph, rank_stats

SOURCE = "第5章 p.102-104（集合的傑出性）"

# 「情報の通り道になっている」と呼ぶ下限。他の人どうしの経路の 1% が通ること。
# 順位（%ile）で切っていたのをやめた。順位は人数で決まるので、経路が 0.04% しか
# 通らない人でも、直接の相手がそれ以上に少なければ上位に出てしまう。
# 実際の値で切れば、通り道と呼べる量が通っている人だけが残る。この 1% は典拠にない。
MIN_BETWEENNESS = 0.01


def compute(g: nx.Graph, group_attr: str = "dept", top_k: int = 10) -> list[Finding]:
    internal = [n for n, data in g.nodes(data=True) if not data.get("is_external")]
    if not internal:
        return []

    # 「ハブとなっている人」と同じ値になるよう、社外も含めたグラフ上で求める
    betw_all = nx.betweenness_centrality(distance_graph(g), weight="distance", normalized=True)
    betw = {n: betw_all.get(n, 0.0) for n in internal}
    # 「人気」= 直接会った相手の数。典拠が言う「同僚からの評価」に対応する観測量
    direct = {n: g.subgraph(internal).degree(n) for n in internal}

    b_stats = rank_stats(betw, higher_is_better=True)
    top_ids = {pid for pid, _ in sorted(betw.items(), key=lambda kv: -kv[1])[:top_k]}

    findings: list[Finding] = []
    for pid, value in betw.items():
        z, pct = b_stats[pid]
        label = g.nodes[pid].get("display_name") or pid
        findings.append(
            Finding(
                feature="influence",
                level="person",
                metric="betweenness",
                entity_id=pid,
                entity_label=label,
                value=round(value, 5),
                direction="higher_is_better",
                status="watch" if pid in top_ids else "ok",
                zscore=z,
                percentile=pct,
                comparison_group="全社",
                comparison_n=len(internal),
                source=SOURCE,
                interprets_as=(
                    f"他の人どうしがつながる経路のうち、{value:.1%} が {label} を通る。"
                    f"直接会ったのは{direct[pid]}名"
                ),
                does_not_mean="この数値は好感度を測っていない。役職の高さとも一致しない",
                caveats=[
                    CALENDAR_CAVEAT,
                    "数えたのは会議に同席した相手だけ。発言量と説得力は測っていない",
                    "観測できていない人が増えると、経路が変わって値も変わる",
                ],
                suggested_actions=(
                    [f"新しい方針を周知するとき、{label} に最初に説明する"]
                    if pid in top_ids
                    else []
                ),
                extra={
                    "dept": g.nodes[pid].get(group_attr),
                    "betweenness": round(value, 5),
                    "direct_contacts": direct[pid],
                },
            )
        )
    return findings


def divergence_ranking(findings: list[Finding], limit: int = 10) -> list[dict]:
    """直接つながっている相手が少ないのに、他の人どうしの経路がよく通る人。

    典拠が言う「少人数でも強力なつながりを持ち、アイデアが遠くまで広がる」人物にあたる。

    選ぶ基準は**実際の値**で、順位は使わない。順位どうしを引き算すると、
    経路が 0.04% しか通らない人も「直接の相手の順位より高い」というだけで上位に出る。
    その人を周知の相手に挙げると、情報は広がらない。
    """
    direct = [
        f.extra.get("direct_contacts")
        for f in findings
        if f.extra.get("direct_contacts") is not None
    ]
    if not direct:
        return []
    median = statistics.median(direct)
    rows = [
        {
            "person_id": f.entity_id,
            "label": f.entity_label,
            "group": f.comparison_group,
            "dept": f.extra.get("dept"),
            "betweenness": f.value,
            "direct": f.extra.get("direct_contacts"),
            "direct_median": median,
        }
        for f in findings
        if (f.value or 0) >= MIN_BETWEENNESS
        and (f.extra.get("direct_contacts") or 0) <= median
    ]
    rows.sort(key=lambda r: -(r["betweenness"] or 0))
    return rows[:limit]

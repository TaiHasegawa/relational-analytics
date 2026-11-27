"""❶ 発想力 — Burt's constraint（典拠: 第5章 p.100-102）。

同席相手どうしが互いに同席していない人ほど、制約の値が低くなる。
典拠によれば、制約の低い社員は、経営陣が新規かつ有効と認めるアイデアを
出す確率が高い。銀行員・弁護士・エンジニアなど複数の職種で確認されている。
"""

from __future__ import annotations

import math

import networkx as nx

from .base import CALENDAR_CAVEAT, ROLE_CAVEAT, Finding, group_members, rank_stats

SOURCE = "Burt (1992) 構造的空隙 / 第5章 p.100-102"


def compute(g: nx.Graph, group_attr: str = "dept") -> list[Finding]:
    internal = [n for n, d in g.nodes(data=True) if not d.get("is_external")]
    sub = g.subgraph(internal)

    raw = nx.constraint(sub, weight="weight")
    eff = nx.effective_size(sub, weight="weight")
    # 「制約 0.085」は思い浮かべられない。同じことを人数の割合で言い直すために使う
    linked = nx.clustering(sub)
    constraint = {n: v for n, v in raw.items() if v is not None and not math.isnan(v)}

    findings: list[Finding] = []
    for group, members in group_members(sub, group_attr).items():
        vals = {m: constraint[m] for m in members if m in constraint}
        if not vals:
            continue
        stats = rank_stats(vals, higher_is_better=False)  # 低いほど良い
        for pid, value in vals.items():
            z, pct = stats[pid]
            diversity = _alter_diversity(sub, pid, group_attr)
            label = sub.nodes[pid].get("display_name") or pid
            findings.append(
                Finding(
                    feature="ideation",
                    level="person",
                    metric="constraint",
                    entity_id=pid,
                    entity_label=label,
                    value=round(value, 4),
                    direction="lower_is_better",
                    status=_status(pct),
                    zscore=z,
                    percentile=pct,
                    comparison_group=group,
                    comparison_n=len(vals),
                    source=SOURCE,
                    interprets_as=f"{label} がつながっている相手どうしが、互いにつながっていない度合い。値が低いほど、互いに接点のない複数の集団に入っている",
                    does_not_mean="この数値は創造性を測っていない。提案する場がなければ、値が低くてもアイデアは出てこない",
                    caveats=[
                        CALENDAR_CAVEAT,
                        ROLE_CAVEAT,
                        f"{group}の{len(vals)}名の中で順位を付けた。人数が少ないと、会議が1〜2件増減するだけで順位が変わる",
                    ],
                    suggested_actions=_actions(pct, label),
                    extra={
                        "effective_size": round(eff.get(pid, 0.0), 3),
                        "degree": sub.degree(pid),
                        "alter_dept_diversity": round(diversity, 3),
                        "alters_linked_share": round(linked.get(pid, 0.0), 3),
                        "alter_dept_count": len(
                            {
                                sub.nodes[nb].get(group_attr) or "(未設定)"
                                for nb in sub.neighbors(pid)
                            }
                        ),
                    },
                )
            )
    return findings


def _alter_diversity(g: nx.Graph, node: str, group_attr: str) -> float:
    """同席相手が何部門に散らばっているかを0〜1で返す（設計 §7.4）。

    1に近いほど、複数の部門に均等に散らばっている。"""
    counts: dict[str, float] = {}
    for nb in g.neighbors(node):
        key = g.nodes[nb].get(group_attr) or "(未設定)"
        counts[key] = counts.get(key, 0.0) + g[node][nb].get("weight", 1.0)
    total = sum(counts.values())
    if total <= 0 or len(counts) < 2:
        return 0.0
    ent = -sum((c / total) * math.log(c / total) for c in counts.values())
    return ent / math.log(len(counts))


def _status(pct: float | None) -> str:
    if pct is None:
        return "ok"
    return "watch" if pct >= 80 else "ok"


def _actions(pct: float | None, who: str) -> list[str]:
    if pct is not None and pct >= 80:
        return [
            "部門をまたぐプロジェクトに参加させる",
            f"担当部門以外の話でも、{who} が持ち込む提案を検討する",
        ]
    return []

"""打ち手を打つと数値がどう変わるかを試算する。

「後継者を同席させる」を、グラフに辺を足すこととして表現し、
「この人がいなくても会議でつながる組の割合」と、切り離される集団の数を再計算する。

これは**グラフ上の定義に照らした計算**であり、予測ではない。
実際にその人が役割を引き継げるかどうかは、この計算では分からない。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import networkx as nx

from .metrics.vulnerability import replaceability


@dataclass
class Step:
    links: int
    replaceability: float
    components_added: int


@dataclass
class Simulation:
    target: str
    successor: str
    successor_label: str
    missing_links: list[str]
    before: float
    after: float
    components_before: int
    components_after: int
    steps: list[Step]
    enough_at: int | None  # 切り離される集団がなくなるのに必要な接点の数

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gain"] = round((self.after - self.before) * 100, 1)
        return d


def _components_added(g: nx.Graph, node: str) -> int:
    """このノードを除くと、つながりが何箇所で切れるか。"""
    h = g.copy()
    h.remove_node(node)
    if h.number_of_nodes() == 0:
        return 0
    return max(nx.number_connected_components(h) - nx.number_connected_components(g), 0)


def succession(
    g: nx.Graph,
    target: str,
    successor: str,
    missing_links: list[str],
    successor_label: str | None = None,
    max_steps: int = 6,
) -> Simulation:
    """後継者を target の接点につないだとき、この人抜きでつながる組がどう変わるか。

    1件ずつ増やして、どこまでやれば十分かを示す。
    """
    links = [x for x in missing_links if x in g and x != successor]
    before = replaceability(g, target)
    comp_before = _components_added(g, target)

    steps: list[Step] = []
    enough: int | None = None
    h = g.copy()
    steps.append(Step(0, round(before, 3), comp_before))
    for i, x in enumerate(links[:max_steps], start=1):
        if not h.has_edge(successor, x):
            h.add_edge(successor, x, weight=1.0)
        r = replaceability(h, target)
        c = _components_added(h, target)
        steps.append(Step(i, round(r, 3), c))
        if enough is None and c == 0 and comp_before > 0:
            enough = i

    after = steps[-1].replaceability
    return Simulation(
        target=target,
        successor=successor,
        successor_label=successor_label or successor,
        missing_links=links[:max_steps],
        before=round(before, 3),
        after=after,
        components_before=comp_before,
        components_after=steps[-1].components_added,
        steps=steps,
        enough_at=enough,
    )


def attach(g: nx.Graph, findings: list) -> None:
    """❻脆弱性の finding に試算を足す。"""
    labels = {n: g.nodes[n].get("display_name") or n for n in g.nodes}
    for f in findings:
        if f.feature != "vulnerability":
            continue
        cands = f.extra.get("succession_candidates") or []
        if not cands:
            continue
        c = cands[0]
        sim = succession(
            g, f.entity_id, c["person_id"], c.get("missing_links") or [],
            successor_label=c.get("label") or labels.get(c["person_id"]),
        )
        f.extra["simulation"] = sim.to_dict()
        if sim.after > sim.before:
            f.suggested_actions.insert(
                0,
                f"{sim.successor_label} を {len(sim.missing_links)}件の接点に同席させる"
                f"（代わりの人がいる相手どうしの組 {sim.before:.0%} → {sim.after:.0%}）",
            )

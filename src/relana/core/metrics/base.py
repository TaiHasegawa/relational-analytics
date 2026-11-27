"""指標の共通基盤。

原則4: 数値だけでなく解釈メタデータを同梱する。
`interprets_as` / `does_not_mean` / `caveats` が過剰解釈を構造的に防ぐ。
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

import networkx as nx


@dataclass
class Finding:
    feature: str  # ideation / influence / team / silo / vulnerability
    level: str  # person / team / org
    metric: str
    entity_id: str
    entity_label: str
    value: float | None
    direction: str = "higher_is_better"  # higher_is_better | lower_is_better | neutral
    threshold: float | None = None
    status: str = "ok"  # ok | watch | warning | critical
    zscore: float | None = None
    percentile: float | None = None
    comparison_group: str | None = None
    comparison_n: int | None = None
    source: str = ""
    interprets_as: str = ""
    does_not_mean: str = ""
    caveats: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def distance_graph(g: nx.Graph) -> nx.Graph:
    """強度グラフを距離グラフに変換する。

    networkx の最短路系アルゴリズムは weight を距離として扱うため、
    強い紐帯ほど「近い」ように反転させる必要がある。
    """
    h = g.copy()
    for _, _, data in h.edges(data=True):
        w = data.get("weight", 1.0)
        data["distance"] = 1.0 / w if w > 0 else float("inf")
    return h


def rank_stats(
    values: dict[str, float], higher_is_better: bool = True
) -> dict[str, tuple[float | None, float | None]]:
    """比較可能な集団内での z値とパーセンタイルを返す。

    FR-5.2: 規模依存の指標は比較可能な集団内でのみランキングする。
    """
    clean = {k: v for k, v in values.items() if v is not None and v == v}
    if len(clean) < 2:
        return {k: (None, None) for k in values}
    vals = list(clean.values())
    mean = statistics.fmean(vals)
    sd = statistics.pstdev(vals)
    ordered = sorted(clean.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    n = len(ordered)
    pct = {k: 100.0 * (1 - i / (n - 1)) if n > 1 else 50.0 for i, (k, _) in enumerate(ordered)}
    out: dict[str, tuple[float | None, float | None]] = {}
    for k in values:
        if k not in clean:
            out[k] = (None, None)
            continue
        z = (clean[k] - mean) / sd if sd > 0 else 0.0
        out[k] = (round(z, 3), round(pct[k], 1))
    return out


def group_members(g: nx.Graph, attr: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for node, data in g.nodes(data=True):
        if data.get("is_external"):
            continue
        key = data.get(attr) or "(未設定)"
        groups.setdefault(key, []).append(node)
    return groups


CALENDAR_CAVEAT = "集計したのは会議の同席だけ。チャット・メール・立ち話は含まない"
ROLE_CAVEAT = "開発やデザインなど会議の少ない職種は、スコアが低く出る。職種をまたいで順位を比べない"

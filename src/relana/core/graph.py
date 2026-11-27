"""グラフ構築（設計 §6）。

2つのグラフを作る。
  G        無向・重み付き   -> ❶発想力 ❷影響力 ❸❹チーム ❺サイロ ❻脆弱性
  G_1on1   n=2 の会議のみ   -> 1on1 サブネットワーク（設計 §7.3）

主催者→参加者の有向グラフは作らない。主催の記録は代理設定や定期会議の
作成者が残るために信頼できず、実測でもマネジャーかどうかでほぼ決まっていた
（r = +0.927）。組織図以上の情報を持たないため使わない。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

import networkx as nx

from ..config import Config
from ..models import Interaction, Person
from .weights import apply_tie_transform, pair_weight


@dataclass
class GraphBundle:
    undirected: nx.Graph
    one_on_one: nx.Graph
    dropped_edges: int = 0
    skipped_large_events: int = 0
    pair_event_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def build_graphs(
    interactions: list[Interaction],
    persons: dict[str, Person],
    cfg: Config,
    window_end: datetime,
) -> GraphBundle:
    gcfg = cfg.graph
    acc: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    acc_1on1: dict[tuple[str, str], float] = defaultdict(float)
    skipped_large = 0

    for ev in interactions:
        attendees = ev.attendees
        n = len(attendees)
        if n < cfg.normalize.min_attendees:
            continue
        if n > cfg.normalize.max_attendees_hard:
            # 分析上の判断ではなく計算量対策。重み関数上すでに実質ゼロ。
            skipped_large += 1
            continue

        days_ago = max((window_end - ev.ts).total_seconds() / 86400.0, 0.0)

        for a, b in combinations(sorted(attendees), 2):
            w = pair_weight(ev, a, b, days_ago, gcfg)
            if w <= 0:
                continue
            k = _key(a, b)
            acc[k] += w
            counts[k] += 1
            if n == 2:
                acc_1on1[k] += w


    G = nx.Graph()
    G1 = nx.Graph()
    for pid, p in persons.items():
        G.add_node(pid, **_node_attrs(p))
        G1.add_node(pid, **_node_attrs(p))

    dropped = 0
    for (a, b), total in acc.items():
        w = apply_tie_transform(total, gcfg.tie_transform)
        # 「何人の会議か」ではなく「関係の証拠が十分か」で辺を張る（設計 §6.3）
        if total < gcfg.min_edge_weight:
            dropped += 1
            continue
        for node in (a, b):
            if node not in G:
                G.add_node(node, **_unknown_attrs(node))
        G.add_edge(a, b, weight=w, raw_weight=total, events=counts[(a, b)])

    for (a, b), total in acc_1on1.items():
        if total < gcfg.min_edge_weight:
            continue
        for node in (a, b):
            if node not in G1:
                G1.add_node(node, **_unknown_attrs(node))
        G1.add_edge(a, b, weight=apply_tie_transform(total, gcfg.tie_transform))


    return GraphBundle(
        undirected=G,
        one_on_one=G1,
        dropped_edges=dropped,
        skipped_large_events=skipped_large,
        pair_event_counts=dict(counts),
    )


def _node_attrs(p: Person) -> dict:
    # 部門は1階層にする。名簿にチームがあれば、それを部門として使う。
    # 本部と課の2階層を画面に並べると、読む人はどちらの話かを決められない。
    # 名簿の上位区分（本部）は family に残し、図の色を同系統にまとめるのにだけ使う。
    unit = p.team or p.dept
    return {
        "dept": unit,
        "team": unit,
        "family": p.dept or unit,
        "role": p.role,
        "display_name": p.display_name,
        "is_external": p.is_external,
    }


def _unknown_attrs(node_id: str) -> dict:
    is_ext = node_id.startswith("ext:")
    return {
        "dept": "(外部)" if is_ext else "(不明)",
        "team": "(外部)" if is_ext else "(不明)",
        "family": "(外部)" if is_ext else "(不明)",
        "role": "",
        # ext: は内部の識別子。画面にはドメインだけを出す
        "display_name": node_id.removeprefix("ext:") if is_ext else node_id,
        "is_external": is_ext,
    }

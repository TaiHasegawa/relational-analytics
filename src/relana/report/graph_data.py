"""インタラクティブなネットワーク図に渡すデータ。

典拠 第5章 p.113 は、ノードとエッジの図からは予測に使えるパターンが見つからないと
指摘している。そこでこの図は「見て終わる図」にせず、6指標で絞り込む操作盤にする。
ノードは指標値を持ち、色・大きさ・絞り込みの基準として使う。
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from ..core.analyze import Snapshot
from ..core.graph import GraphBundle
from .layout import DISPLAY_MIN_WEIGHT, compute as compute_layout, display_edges, place_labels


def build(snap: Snapshot, bundle: GraphBundle, group_attr: str = "dept") -> dict[str, Any]:
    g = bundle.undirected
    metrics = _metrics_by_person(snap)
    roles = snap.roles or {}
    shown = display_edges(g, DISPLAY_MIN_WEIGHT)
    lay = compute_layout(g, group_attr, DISPLAY_MIN_WEIGHT)
    pos = lay["pos"]

    internal = [n for n, d in g.nodes(data=True) if not d.get("is_external")]
    nodes: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for n in sorted(g.nodes):
        d = g.nodes[n]
        m = metrics.get(n, {})
        index[n] = len(nodes)
        xy = pos.get(n, [0.0, 0.0])
        nodes.append(
            {
                "id": n,
                "label": d.get("display_name") or n,
                "x": xy[0],
                "y": xy[1],
                "dept": d.get("dept") or "(未設定)",
                "team": d.get("team") or "(未設定)",
                "role": d.get("role") or "",
                "external": bool(d.get("is_external")),
                "roles": [r["label"] for r in roles.get(n, {}).get("roles", [])],
                # 1人の打ち手はここに集める。役割をまたいで同じ文面は1回だけ出す
                "actions": list(
                    dict.fromkeys(
                        a
                        for r in roles.get(n, {}).get("roles", [])
                        for a in r["actions"]
                    )
                )[:4],
                "degree": g.degree(n),
                "strength": round(g.degree(n, weight="weight"), 2),
                **m,
            }
        )

    links: list[dict[str, Any]] = []
    hidden = 0
    for a, b, data in g.edges(data=True):
        key = (a, b) if a <= b else (b, a)
        if key not in shown:
            hidden += 1
            continue
        links.append(
            {
                "s": index[a],
                "t": index[b],
                "w": round(data.get("weight", 1.0), 3),
                "n": data.get("events", 0),
                "dyad": bundle.one_on_one.has_edge(a, b),
                "cross": (g.nodes[a].get(group_attr) != g.nodes[b].get(group_attr)),
            }
        )

    # 代表的な人に印を付ける。氏名を常に出す対象。
    # 全員分を常時出すと重なって読めないため、ここで絞る。
    ranked = sorted(
        (n for n in nodes if not n["external"]), key=lambda n: -(n.get("degree") or 0)
    )
    top_n = max(10, len(internal) // 8)
    hubs = {n["id"] for n in ranked[:top_n]}
    for n in nodes:
        n["key"] = bool(
            n["external"] or n.get("critical") in ("critical", "warning") or n["id"] in hubs
        )

    # 氏名ラベルを重ならないように配置する。場所を確保する順番は
    # ❻で検出された人 -> 社外 -> 同席相手の多い人 の順。
    def priority(n: dict) -> tuple:
        return (
            0 if n.get("critical") == "critical" else (1 if n["external"] else 2),
            -(n.get("degree") or 0),
            n["id"],
        )

    order = [
        (n["id"], n["label"], _radius(n))
        for n in sorted(nodes, key=priority)
    ]
    labels = place_labels({n["id"]: (n["x"], n["y"]) for n in nodes}, order)

    depts: dict[str, int] = {}
    family: dict[str, str] = {}
    for n in sorted(g.nodes):
        d = g.nodes[n]
        if d.get("is_external"):
            continue
        name = d.get("dept") or "(未設定)"
        depts[name] = depts.get(name, 0) + 1
        family.setdefault(name, d.get("family") or name)

    return {
        "snapshot": snap.snapshot_id,
        "window": [snap.window_start, snap.window_end],
        "nodes": nodes,
        "links": links,
        "labels": labels,
        "clusters": lay["groups"],
        "bounds": lay["bounds"],
        "min_weight": DISPLAY_MIN_WEIGHT,
        "hidden_links": hidden,
        "depts": _dept_legend(depts, family),
        "stats": {
            "people": len(internal),
            "key_nodes": sum(1 for n in nodes if n["key"]),
            "edges": len(links),
            "hidden": hidden,
            "labelled": len(labels),
            "dyads": sum(1 for l in links if l["dyad"]),
            "cross": sum(1 for l in links if l["cross"]),
            "max_weight": max((l["w"] for l in links), default=1.0),
        },
    }


def _radius(n: dict[str, Any]) -> float:
    """ラベル配置で使う半径。描画側の既定（同席相手の数）に合わせる。"""
    if n["external"]:
        return 7.0
    import math

    return 4 + math.sqrt(max(n.get("degree") or 0, 0) / 28) * 11


def _metrics_by_person(snap: Snapshot) -> dict[str, dict[str, Any]]:
    """各人の指標値を1つの辞書にまとめる。図の色・大きさ・絞り込みに使う。"""
    out: dict[str, dict[str, Any]] = {}
    for f in snap.findings:
        if f.level != "person":
            continue
        rec = out.setdefault(f.entity_id, {})
        if f.metric == "constraint":
            rec["constraint"] = round(f.value, 4) if f.value is not None else None
            rec["constraint_pct"] = f.percentile
            rec["alter_depts"] = f.extra.get("alter_dept_count")
            rec["alters_linked"] = f.extra.get("alters_linked_share")
        elif f.metric == "betweenness":
            rec["betweenness"] = f.value
            rec["direct"] = f.extra.get("direct_contacts")
    for f in snap.findings:
        if f.feature != "vulnerability":
            continue
        rec = out.setdefault(f.entity_id, {})
        rec["replaceability"] = f.extra.get("replaceability")
        rec["dept_pairs_kept"] = f.extra.get("dept_pairs_kept")
        rec["dept_pairs"] = f.extra.get("dept_pairs")
        rec["critical"] = f.status
        rec["sole_external"] = len(f.extra.get("sole_external_contacts") or [])
        rec["bridged"] = [
            b["group"] for b in (f.extra.get("bridged_groups") or []) if b.get("sole_bridge")
        ]
    return out


# 部門の色。同じ上位区分（名簿の dept 列）だった部門は同じ色味にそろえ、
# 明るさを変えて1部門ずつ別の色にする。色を使い回すと、離れた2部門が
# 同じ色になり、図の上で同じ部門に見える。
_HUES = [
    (202, 53),  # 青
    (31, 80),   # 橙
    (147, 32),  # 緑
    (276, 31),  # 紫
    (328, 45),  # 桃
    (20, 31),   # 茶
    (39, 62),   # 黄
    (190, 30),  # 藍
    (95, 30),   # 黄緑
    (250, 35),  # 青紫
]
# 明るさの幅。同じ色味の中で何部門あっても、この範囲いっぱいに散らす。
# 刻みを固定すると、2部門だけの色味で差が小さくなり、2つが同じ色に見える。
_L_MIN, _L_MAX = 30.0, 62.0
_H_SPREAD = 16.0


def _dept_legend(counts: dict[str, int], family: dict[str, str]) -> list[dict[str, Any]]:
    """凡例の並びと色。上位区分ごとにまとめ、人数の多い順に並べる。"""
    fams: dict[str, list[str]] = {}
    for name in sorted(counts, key=lambda k: -counts[k]):
        fams.setdefault(family.get(name, name), []).append(name)
    order = sorted(fams, key=lambda f: -sum(counts[n] for n in fams[f]))
    out: list[dict[str, Any]] = []
    for fi, fam in enumerate(order):
        members = fams[fam]
        hue, sat = _HUES[fi % len(_HUES)]
        span = len(members) - 1
        for mi, name in enumerate(members):
            # 1部門だけの区分は幅の中央。2部門以上なら幅の端から端まで使う
            frac = 0.5 if span == 0 else mi / span
            light = _L_MIN + (_L_MAX - _L_MIN) * frac
            out.append({
                "name": name,
                "count": counts[name],
                "family": fam,
                "color": f"hsl({hue + (frac - 0.5) * _H_SPREAD:.0f} {sat}% {light:.0f}%)",
            })
    return out

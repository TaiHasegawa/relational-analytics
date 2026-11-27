"""分析オーケストレーション。スナップショットを生成する（原則7）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..config import Config
from ..models import CollectionReport, Interaction, Person
from .graph import GraphBundle, build_graphs
from .metrics import ideation, influence, silo, team, vulnerability
from .metrics.base import Finding


@dataclass
class Snapshot:
    snapshot_id: str
    window_start: str
    window_end: str
    window_days: int
    config_hash: str
    code_version: str
    privacy_level: str
    groups_source: str = "provided"
    reliability: dict[str, Any] = field(default_factory=dict)
    roles: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    highlights: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


def analyze(
    interactions: list[Interaction],
    persons: list[Person],
    cfg: Config,
    window_end: datetime,
    snapshot_id: str = "adhoc",
    collection: CollectionReport | None = None,
    normalize_report: Any | None = None,
    headcount: int | None = None,
) -> tuple[Snapshot, GraphBundle]:
    by_id = {p.person_id: p for p in persons if not p.is_bot}
    bundle = build_graphs(interactions, by_id, cfg, window_end)

    g = bundle.undirected
    findings: list[Finding] = []
    findings += ideation.compute(g, cfg.analysis.group_by)
    findings += influence.compute(g, cfg.analysis.group_by)
    findings += team.compute(g, cfg.analysis.team_by)
    findings += silo.compute(
        g,
        cfg.analysis.group_by,
        cfg.analysis.silo_threshold,
        groups_inferred=cfg.analysis.groups_source == "inferred",
    )
    findings += vulnerability.compute(
        g, meeting_load=_meeting_load(interactions), group_attr=cfg.analysis.group_by
    )
    # 打ち手を打つと数値がどう変わるかを試算して、finding に添える
    from .simulate import attach as attach_simulation

    attach_simulation(g, findings)

    window_start = window_end - timedelta(days=cfg.window_days)
    snap = Snapshot(
        snapshot_id=snapshot_id,
        window_start=window_start.date().isoformat(),
        window_end=window_end.date().isoformat(),
        window_days=cfg.window_days,
        config_hash=cfg.fingerprint(),
        code_version="0.1.0",
        privacy_level=cfg.analysis.privacy_level,
        groups_source=cfg.analysis.groups_source,
        findings=findings,
    )
    snap.quality = _quality(interactions, by_id, bundle, collection, normalize_report)
    from .reliability import assess

    snap.reliability = assess(
        observed=snap.quality["persons_observed"],
        headcount=headcount,
        with_edges=snap.quality["persons_with_edges"],
    ).to_dict()
    snap.highlights = _highlights(findings, bundle)

    # 役割は6指標の組み合わせから決まるため、指標が揃ったあとに判定する
    from .roles import assign as assign_roles, missing_roles, priority

    people = assign_roles(snap, bundle, interactions, group_attr=cfg.analysis.group_by)
    snap.roles = {k: v.to_dict() for k, v in people.items()}
    snap.highlights["priority_people"] = [p.to_dict() for p in priority(people)]
    snap.highlights["dept_roles"] = missing_roles(people, g, cfg.analysis.group_by)

    from .summary import build as build_examples

    snap.highlights["examples"] = build_examples(findings, snap.highlights)
    return snap, bundle


def _meeting_load(interactions: list[Interaction]) -> dict[str, float]:
    """会議負荷（分）。❻脆弱性の補強指標としてのみ使う（設計 §7.4）。"""
    load: dict[str, float] = {}
    for ev in interactions:
        minutes = ev.duration_min or 0
        for pid in ev.attendees:
            load[pid] = load.get(pid, 0.0) + minutes
    return load


def _quality(
    interactions: list[Interaction],
    persons: dict[str, Person],
    bundle: GraphBundle,
    collection: CollectionReport | None,
    normalize_report: Any | None,
) -> dict[str, Any]:
    # 外部エンティティは「社員数」に含めない（規模の警告が誤発火するため）
    persons = {k: v for k, v in persons.items() if not v.is_external}
    observed = {
        pid for ev in interactions for pid in ev.attendees if not pid.startswith("ext:")
    } & set(persons)
    internal_nodes = [n for n, a in bundle.undirected.nodes(data=True) if not a.get("is_external")]
    connected = [n for n in internal_nodes if bundle.undirected.degree(n) > 0]
    sizes: dict[int, int] = {}
    for ev in interactions:
        sizes[ev.participant_count] = sizes.get(ev.participant_count, 0) + 1
    types: dict[str, int] = {}
    for ev in interactions:
        types[ev.meeting_type] = types.get(ev.meeting_type, 0) + 1

    q = {
        "persons_in_master": len(persons),
        "persons_observed": len(observed),
        "coverage_rate": round(len(observed) / len(persons), 3) if persons else 0.0,
        "persons_with_edges": len(connected),
        "edge_coverage_rate": round(len(connected) / len(persons), 3) if persons else 0.0,
        "interactions": len(interactions),
        "edges": bundle.undirected.number_of_edges(),
        "edges_dropped_below_threshold": bundle.dropped_edges,
        "one_on_one_edges": bundle.one_on_one.number_of_edges(),
        "skipped_large_events": bundle.skipped_large_events,
        "meeting_size_histogram": dict(sorted(sizes.items())),
        "meeting_type_counts": dict(sorted(types.items(), key=lambda kv: -kv[1])),
    }
    if collection:
        q["collection"] = asdict(collection)
    if normalize_report is not None:
        q["normalize"] = asdict(normalize_report)
    return q


def _highlights(findings: list[Finding], bundle: GraphBundle) -> dict[str, Any]:
    silos = [
        f
        for f in findings
        if f.metric == "ie_ratio" and f.status in ("warning", "critical")
    ]
    crit = [f for f in findings if f.feature == "vulnerability"]
    inf = [f for f in findings if f.feature == "influence"]
    return {
        "siloed_depts": sorted(
            (
                {
                    "dept": f.entity_id,
                    "ie_ratio": f.value,
                    "display": f.extra.get("display"),
                    "times_random": f.extra.get("times_random_display"),
                    "status": f.status,
                }
                for f in silos
            ),
            key=lambda r: -(r["ie_ratio"] if r["ie_ratio"] is not None else float("inf")),
        ),
        "critical_persons": sorted(
            (
                {
                    "person_id": f.entity_id,
                    "label": f.entity_label,
                    "dept": f.extra.get("dept"),
                    "replaceability": f.extra.get("replaceability"),
                    "dept_pairs_kept": f.extra.get("dept_pairs_kept"),
                    "dept_pairs": f.extra.get("dept_pairs"),
                    "status": f.status,
                }
                for f in crit
            ),
            key=lambda r: (
                r["dept_pairs_kept"] if r["dept_pairs_kept"] is not None else 1.1,
                r["replaceability"],
            ),
        ),
        "influence_divergence": influence.divergence_ranking(inf),
        "isolated_persons": [
            n
            for n, a in bundle.one_on_one.nodes(data=True)
            if not a.get("is_external") and bundle.one_on_one.degree(n) == 0
        ],
    }

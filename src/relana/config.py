"""分析設定。単一のYAMLで完結する（FR-10.1）。

既定値は docs/design-google-calendar.md の §5.2 / §6.2 / §6.3 に対応する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class SizeDecay:
    """参加人数による減衰（設計 §5.2）。

    n0: 会議が「対話」から「一方向の情報伝達」に変わる人数
    k : 相転移の滑らかさ
    """

    n0: float = 10.0
    k: float = 3.0


@dataclass
class GraphConfig:
    size_decay: SizeDecay = field(default_factory=SizeDecay)
    duration_beta: float = 0.5  # 0=時間無視 / 0.5=逓減 / 1=線形
    response_weight: dict[str, float] = field(
        default_factory=lambda: {
            "accepted": 1.0,
            "tentative": 0.6,
            "needsAction": 0.8,
        }
    )
    half_life_days: float = 90.0  # 窓長と同じ。窓の先頭でも0.5に留める
    min_edge_weight: float = 0.3
    tie_transform: str = "linear"  # linear | sqrt | log


@dataclass
class NormalizeConfig:
    drop_resources: bool = True
    drop_declined: bool = True
    min_attendees: int = 2
    max_attendees_hard: int = 50  # 計算量対策のみ。分析上の閾値ではない
    external_domains_as_entity: bool = True
    exclude_all_day: bool = True
    internal_domains: list[str] = field(default_factory=list)
    # 定期グループ会議のタイトルを保持するか（組織構造の推定にのみ使う）。
    # 既定オフ。有効にする場合は収集範囲が広がることを利用者に説明すること。
    keep_group_titles: bool = False
    group_title_min_attendees: int = 3
    # Google Workspace のグループ（sales@ info@ など）を参加者から落とす。
    # 人ではないので、残すと人数を水増しし中心性も歪める。
    drop_group_addresses: bool = True
    # 追加で落とすアドレス（確認の結果グループだと判明したもの）
    extra_group_addresses: list[str] = field(default_factory=list)


@dataclass
class AnalysisConfig:
    privacy_level: str = "L2"
    group_by: str = "dept"
    team_by: str = "team"
    silo_threshold: float = 5.0
    one_on_one_subgraph: bool = True
    # 部門・チームが利用者の確認を経たものか、カレンダーからの推定か。
    # 推定のままサイロ診断を行うと循環論法になるため、結果に注記を出す。
    groups_source: str = "provided"  # provided | inferred


@dataclass
class Config:
    window_days: int = 90
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        with open(path, encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Config":
        cfg = cls()
        cfg.window_days = raw.get("collect", {}).get("window_days", cfg.window_days)

        n = raw.get("normalize", {})
        for key in (
            "drop_resources",
            "drop_declined",
            "min_attendees",
            "max_attendees_hard",
            "external_domains_as_entity",
            "exclude_all_day",
            "internal_domains",
            "keep_group_titles",
            "group_title_min_attendees",
            "drop_group_addresses",
            "extra_group_addresses",
        ):
            if key in n:
                setattr(cfg.normalize, key, n[key])

        g = raw.get("graph", {})
        if "size_decay" in g:
            cfg.graph.size_decay = SizeDecay(**g["size_decay"])
        for key in (
            "duration_beta",
            "response_weight",
            "half_life_days",
            "min_edge_weight",
            "tie_transform",
        ):
            if key in g:
                setattr(cfg.graph, key, g[key])

        a = raw.get("analysis", {})
        for key in (
            "privacy_level",
            "group_by",
            "team_by",
            "silo_threshold",
            "one_on_one_subgraph",
            "groups_source",
        ):
            if key in a:
                setattr(cfg.analysis, key, a[key])
        return cfg

    def fingerprint(self) -> str:
        """設定ハッシュ。スナップショットの比較可能性判定に使う（FR-6.3）。"""
        import hashlib
        import json

        def enc(o: Any) -> Any:
            if hasattr(o, "__dataclass_fields__"):
                return {k: enc(getattr(o, k)) for k in o.__dataclass_fields__}
            return o

        blob = json.dumps(enc(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

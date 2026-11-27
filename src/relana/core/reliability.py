"""指標の信頼度を被覆率から判定する。

ネットワーク指標は欠損に対して一様に強いわけではない。
**媒介中心性と制約は、ノードが欠けると急速に劣化する**ことが知られている
（ネットワーク指標の誤差耐性に関する一連の研究）。一方で、部門単位の集計指標は
比較的頑健である。

本OSSは芋づる式に収集するため、被覆が不完全な状態で分析されるのが前提になる。
**どの指標がどこまで信用できるかを、結果に添えて出す**必要がある。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 指標ごとの欠損への弱さ（1.0 = 最も弱い）
# ego ネットワークや最短経路に依存する指標ほど、ノードが欠けると壊れる
FRAGILITY = {
    "vulnerability": 1.00,  # 媒介中心性・連結性。欠損ノードが経路を変える
    "ideation": 0.85,       # 制約。alter が欠けると ego ネットワークが別物になる
    "influence": 0.70,      # PageRank。全体構造に依存するが集約的
    "team": 0.55,           # チーム内に閉じるため、全体の欠損には比較的強い
    "silo": 0.35,           # 部門単位の集計。個々のノード欠損の影響が薄まる
}

LEVELS = (
    (0.85, "high", "高い", "個人ごとのスコアを判断に使える"),
    (0.70, "medium", "中程度", "個人の順位は数位ずれる。上位5名・下位5名という範囲で見る"),
    (0.50, "low", "低い", "個人ごとのスコアは使わない。部門単位の集計だけを見る"),
    (0.00, "insufficient", "不足", "部門単位の集計も実態とずれる。カレンダーを追加で収集する"),
)


@dataclass
class Reliability:
    coverage: float
    observed: int
    headcount: int | None

    def level(self, feature: str) -> dict[str, Any]:
        """指標ごとの実効的な信頼度。欠損に弱い指標ほど厳しく判定する。"""
        fragility = FRAGILITY.get(feature, 0.7)
        # 弱い指標ほど、同じ被覆率でも実効的な信頼度を下げる
        effective = self.coverage ** (0.5 + fragility)
        for threshold, key, label, advice in LEVELS:
            if effective >= threshold:
                return {
                    "key": key,
                    "label": label,
                    "advice": advice,
                    "effective": round(effective, 3),
                    "fragility": fragility,
                }
        return {"key": "insufficient", "label": "不足", "advice": LEVELS[-1][3], "effective": 0.0}

    def person_level_ok(self, feature: str) -> bool:
        return self.level(feature)["key"] in ("high", "medium")

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": round(self.coverage, 3),
            "observed": self.observed,
            "headcount": self.headcount,
            "by_feature": {f: self.level(f) for f in FRAGILITY},
            "note": (
                "媒介中心性と制約は、観測できていない人が増えると値が変わる。"
                "部門単位の集計は、数名欠けても比率がほぼ変わらない。"
            ),
        }


def assess(observed: int, headcount: int | None, with_edges: int | None = None) -> Reliability:
    """被覆率を求める。従業員数が分かっていればそれを分母にする。

    分母が無い場合は「観測した中で関係が付いた割合」になるが、
    これは発見した範囲に依存する循環した値であり、過大評価になりやすい。
    """
    base = headcount or observed or 1
    numerator = with_edges if with_edges is not None else observed
    return Reliability(
        coverage=min(numerator / base, 1.0), observed=observed, headcount=headcount
    )

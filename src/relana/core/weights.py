"""エッジ重みの計算（設計 §5.2 / §6.2）。

重みは4つの独立した効果の積で表す。

    w = w_size(n) x w_dur(d) x w_resp(i,j) x w_time(t)

参加人数を閾値で切らず連続関数で扱うのが本モジュールの要点。
3名と10名の会議は性質が違い、10名と11名の間に断絶があるわけでもない。
"""

from __future__ import annotations

import math

from ..config import GraphConfig
from ..models import Interaction


def sigma(n: float, n0: float, k: float) -> float:
    """対話 -> 一方向への相転移を表すロジスティック減衰。

    少人数の会議は全員が相互に話すが、人数が増えるとある時点で
    「発表と傾聴」に変わり、2人の参加者が一言も交わさない状態になる。
    時間分割 1/(n-1) だけでは表現できないこの効果を担う。
    """
    return 1.0 / (1.0 + math.exp((n - n0) / k))


def size_weight(n: int, n0: float = 10.0, k: float = 3.0) -> float:
    """参加人数 n の会議における1ペアあたりの重み。1on1 を 1.0 に正規化する。

        w_size(n) = sigma(n) / (n - 1)   を w_size(2) で割ったもの

    1/(n-1) は時間分割（Newman の共著ネットワークと同じ論理）、
    sigma(n) は対話->一方向の相転移を表す。

    >>> round(size_weight(2), 3)
    1.0
    >>> round(size_weight(10), 3)   # 相転移点。1on1 の約 1/17
    0.059
    >>> size_weight(30) < 1e-4      # ハード閾値なしで実質ゼロになる
    True
    """
    if n < 2:
        return 0.0
    base = sigma(2, n0, k) / 1.0
    return (sigma(n, n0, k) / (n - 1)) / base


def duration_weight(duration_min: int | None, beta: float = 0.5) -> float:
    """所要時間の重み。60分を基準に逓減させる。

    beta=0 で時間を無視（回数ベース）、beta=1 で線形。
    既定 0.5 は「長時間ほど関係は強いが比例はしない」という逓減を表す。
    """
    if duration_min is None or duration_min <= 0:
        return 1.0
    if beta == 0:
        return 1.0
    return (duration_min / 60.0) ** beta


def response_weight(status: str, table: dict[str, float]) -> float:
    """返答状況の重み。declined は正規化段階で既に除外済み。"""
    return table.get(status, 1.0)


def time_decay(days_ago: float, half_life_days: float) -> float:
    """時間減衰。関係は動的であり、古い接触ほど現在の関係を説明しない。"""
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (days_ago / half_life_days)


def pair_weight(
    ev: Interaction,
    person_a: str,
    person_b: str,
    days_ago: float,
    cfg: GraphConfig,
) -> float:
    """1イベントが1ペアに与える重み。"""
    w = size_weight(ev.participant_count, cfg.size_decay.n0, cfg.size_decay.k)
    w *= duration_weight(ev.duration_min, cfg.duration_beta)
    w *= response_weight(ev.responses.get(person_a, "accepted"), cfg.response_weight)
    w *= response_weight(ev.responses.get(person_b, "accepted"), cfg.response_weight)
    w *= time_decay(days_ago, cfg.half_life_days)
    return w


def apply_tie_transform(total: float, transform: str) -> float:
    """累積した紐帯強度への変換。

    線形だと週次1on1の相手がエゴネットワークの重みを独占し、
    制約スコア(❶)が過度に低く出る懸念がある。感度分析で確認する対象。
    """
    if transform == "sqrt":
        return math.sqrt(total)
    if transform == "log":
        return math.log1p(total)
    return total

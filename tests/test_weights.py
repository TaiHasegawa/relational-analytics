"""重み関数の既知値テスト（設計 §5.2 の表と一致すること）。"""

import math

import pytest

from relana.core.weights import apply_tie_transform, duration_weight, size_weight, time_decay

# 設計書 §5.2 の表。この値が変わる = 設計変更であり、意図的でなければ退行
EXPECTED = {
    2: 1.0000,
    3: 0.4875,
    4: 0.3140,
    5: 0.2249,
    6: 0.1693,
    7: 0.1303,
    8: 0.1010,
    10: 0.0594,
    12: 0.0330,
    15: 0.0121,
    20: 0.0019,
}


@pytest.mark.parametrize("n,expected", EXPECTED.items())
def test_size_weight_matches_design(n, expected):
    assert size_weight(n) == pytest.approx(expected, abs=5e-4)


def test_one_on_one_is_the_unit():
    assert size_weight(2) == pytest.approx(1.0)


def test_large_meetings_vanish_without_a_hard_cutoff():
    """ハード閾値を置かずとも、大人数会議は自動的に実質ゼロになる。"""
    assert size_weight(30) < 1e-4
    assert size_weight(100) < 1e-9


def test_size_weight_is_monotonically_decreasing():
    vals = [size_weight(n) for n in range(2, 60)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_n0_shifts_the_transition_point():
    """n0 は「会議が一方向になる人数」。大きくすると大人数会議も重く扱われる。"""
    assert size_weight(12, n0=15) > size_weight(12, n0=10)


def test_duration_weight_diminishes():
    assert duration_weight(60) == pytest.approx(1.0)
    assert duration_weight(120) == pytest.approx(math.sqrt(2), abs=1e-6)
    assert duration_weight(120) < 2 * duration_weight(60)  # 比例しない
    assert duration_weight(60, beta=0) == 1.0
    assert duration_weight(None) == 1.0


def test_time_decay():
    assert time_decay(0, 90) == 1.0
    assert time_decay(90, 90) == pytest.approx(0.5)
    assert time_decay(10, 0) == 1.0  # 無効値でも落ちない


def test_tie_transform():
    assert apply_tie_transform(9.0, "linear") == 9.0
    assert apply_tie_transform(9.0, "sqrt") == 3.0
    assert apply_tie_transform(0.0, "log") == 0.0

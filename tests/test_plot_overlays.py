"""plot_overlays: trendline math + reference levels."""
import math
import numpy as np
import pytest

from src import plot_overlays as ov


def test_linear_recovers_perfect_fit():
    xs = list(range(10))
    ys = [3.0 * x + 2.0 for x in xs]
    out = ov.trendline(ov.TREND_LINEAR, xs, ys)
    assert out is not None
    _, _, (m, b), r2 = out
    assert abs(m - 3.0) < 1e-9
    assert abs(b - 2.0) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


def test_polynomial_deg2_recovers_parabola():
    xs = list(range(10))
    ys = [(x - 5) ** 2 + 1 for x in xs]
    out = ov.trendline(ov.TREND_POLY2, xs, ys)
    assert out is not None
    _, _, params, r2 = out
    assert abs(params[0] - 1.0) < 1e-9   # leading coef
    assert abs(r2 - 1.0) < 1e-9


def test_exponential_fit_recovers_a_b():
    xs = list(range(10))
    ys = [2.0 * math.exp(0.5 * x) for x in xs]
    out = ov.trendline(ov.TREND_EXP, xs, ys)
    assert out is not None
    _, _, (a, b), r2 = out
    assert abs(a - 2.0) < 1e-6
    assert abs(b - 0.5) < 1e-6
    assert abs(r2 - 1.0) < 1e-9


def test_logarithmic_fit_recovers_a_b():
    xs = list(range(1, 11))
    ys = [3.0 * math.log(x) + 1.0 for x in xs]
    out = ov.trendline(ov.TREND_LOG, xs, ys)
    assert out is not None
    _, _, (a, b), r2 = out
    assert abs(a - 3.0) < 1e-9
    assert abs(b - 1.0) < 1e-9


def test_moving_average_smooths_step():
    ys = [0.0] * 10 + [1.0] * 10
    out = ov.moving_average(list(range(20)), ys, window=5)
    assert out is not None
    _, smooth, (window,), r2 = out
    assert window == 5
    assert r2 is None
    assert smooth.min() < 0.5 and smooth.max() > 0.5


@pytest.mark.parametrize("kind,xs,ys", [
    (ov.TREND_LINEAR, [1, 1, 1], [1, 2, 3]),       # zero-variance x
    (ov.TREND_POLY3, [1, 2], [1, 4]),              # too few points
    (ov.TREND_EXP, [1, 2, 3], [-1, -2, -3]),       # non-positive y
    (ov.TREND_LOG, [-1, -2, -3], [1, 2, 3]),       # non-positive x
])
def test_trendline_returns_none_on_degenerate(kind, xs, ys):
    assert ov.trendline(kind, xs, ys) is None


def test_equation_text_per_kind():
    assert "y = " in ov.equation_text(ov.TREND_LINEAR, (1.0, 2.0))
    assert "x²" in ov.equation_text(ov.TREND_POLY2, (1.0, 2.0, 3.0))
    assert "exp(" in ov.equation_text(ov.TREND_EXP, (1.0, 2.0))
    assert "ln(x)" in ov.equation_text(ov.TREND_LOG, (1.0, 2.0))
    assert "window=" in ov.equation_text(ov.TREND_MA, (5,))


def test_reference_levels_mean_and_median():
    levels = ov.reference_levels([1, 2, 3, 4, 5], mean=True, median=True)
    assert len(levels) == 2
    assert abs(levels[0][1] - 3.0) < 1e-9
    assert abs(levels[1][1] - 3.0) < 1e-9


def test_reference_levels_nan_safe():
    levels = ov.reference_levels([float("nan"), 1, 2, 3], mean=True, median=False)
    assert abs(levels[0][1] - 2.0) < 1e-9


def test_reference_levels_empty_input():
    assert ov.reference_levels([], mean=True, median=True) == []

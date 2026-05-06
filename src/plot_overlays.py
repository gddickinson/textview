"""Trendlines + reference-line analysis overlays for `PlotDialog`.

Pure numerical helpers — no matplotlib or Qt imports — so they can be
unit-tested headlessly. Each `fit_*` returns `(x_line, y_line, params, r2)`
or `None` when the data doesn't support the model (too few points, zero
variance, non-positive y for log/exp, …). Callers paint the returned
arrays however they like and use `equation_text(kind, params)` for the
legend label.
"""
from __future__ import annotations
import math
import numpy as np


TREND_NONE = "None"
TREND_LINEAR = "Linear"
TREND_POLY2 = "Polynomial (deg 2)"
TREND_POLY3 = "Polynomial (deg 3)"
TREND_EXP = "Exponential"
TREND_LOG = "Logarithmic"
TREND_MA = "Moving average"
TREND_TYPES = [TREND_NONE, TREND_LINEAR, TREND_POLY2, TREND_POLY3,
               TREND_EXP, TREND_LOG, TREND_MA]


def _clean(xs, ys):
    x = np.asarray(xs, dtype=float); y = np.asarray(ys, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    return x[mask], y[mask]


def _r2(y, pred):
    y = np.asarray(y, dtype=float); pred = np.asarray(pred, dtype=float)
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def fit_polynomial(xs, ys, degree: int):
    x, y = _clean(xs, ys)
    if len(x) < degree + 1: return None
    if x.var() == 0: return None
    coeffs = np.polyfit(x, y, degree)
    poly = np.poly1d(coeffs)
    r2 = _r2(y, poly(x))
    x_line = np.linspace(x.min(), x.max(), 200)
    return x_line, poly(x_line), tuple(coeffs), r2


def fit_exponential(xs, ys):
    """y ≈ a · exp(b · x), fit by linearizing log(y) = log(a) + b·x."""
    x, y = _clean(xs, ys)
    pos = y > 0
    if pos.sum() < 2: return None
    x, y = x[pos], y[pos]
    if x.var() == 0: return None
    b, log_a = np.polyfit(x, np.log(y), 1)
    a = math.exp(log_a)
    pred = a * np.exp(b * x)
    r2 = _r2(y, pred)
    x_line = np.linspace(x.min(), x.max(), 200)
    return x_line, a * np.exp(b * x_line), (a, b), r2


def fit_logarithmic(xs, ys):
    """y ≈ a · ln(x) + b, requires x > 0."""
    x, y = _clean(xs, ys)
    pos = x > 0
    if pos.sum() < 2: return None
    x, y = x[pos], y[pos]
    if np.log(x).var() == 0: return None
    a, b = np.polyfit(np.log(x), y, 1)
    pred = a * np.log(x) + b
    r2 = _r2(y, pred)
    x_line = np.linspace(x.min(), x.max(), 200)
    return x_line, a * np.log(x_line) + b, (a, b), r2


def moving_average(xs, ys, window: int = 5):
    """Trailing simple moving average. Returns None if y shorter than window."""
    x, y = _clean(xs, ys)
    if len(y) < window or window < 2: return None
    # Sort by x to make a sensible MA when xs aren't monotonic.
    order = np.argsort(x)
    x, y = x[order], y[order]
    kernel = np.ones(window) / window
    smooth = np.convolve(y, kernel, mode="valid")
    x_smooth = x[window - 1:]
    return x_smooth, smooth, (window,), None


def trendline(kind: str, xs, ys, *, ma_window: int = 5):
    """Dispatch to the right `fit_*` and return its (x, y, params, r2)."""
    if kind == TREND_LINEAR: return fit_polynomial(xs, ys, 1)
    if kind == TREND_POLY2:  return fit_polynomial(xs, ys, 2)
    if kind == TREND_POLY3:  return fit_polynomial(xs, ys, 3)
    if kind == TREND_EXP:    return fit_exponential(xs, ys)
    if kind == TREND_LOG:    return fit_logarithmic(xs, ys)
    if kind == TREND_MA:     return moving_average(xs, ys, window=ma_window)
    return None


def equation_text(kind: str, params) -> str:
    if params is None: return ""
    if kind == TREND_LINEAR:
        m, b = params
        return f"y = {m:.3g}·x + {b:.3g}"
    if kind == TREND_POLY2:
        a, b, c = params
        return f"y = {a:.3g}·x² + {b:.3g}·x + {c:.3g}"
    if kind == TREND_POLY3:
        a, b, c, d = params
        return f"y = {a:.3g}·x³ + {b:.3g}·x² + {c:.3g}·x + {d:.3g}"
    if kind == TREND_EXP:
        a, b = params
        return f"y = {a:.3g}·exp({b:.3g}·x)"
    if kind == TREND_LOG:
        a, b = params
        return f"y = {a:.3g}·ln(x) + {b:.3g}"
    if kind == TREND_MA:
        (window,) = params
        return f"MA(window={window})"
    return ""


def reference_levels(ys, *, mean: bool, median: bool) -> list[tuple[str, float]]:
    """Return [(label, y-value), …] for whichever reference lines are on."""
    arr = np.asarray([v for v in ys if v == v], dtype=float)  # NaN-safe
    if arr.size == 0: return []
    out = []
    if mean:   out.append((f"mean = {arr.mean():.3g}",   float(arr.mean())))
    if median: out.append((f"median = {np.median(arr):.3g}", float(np.median(arr))))
    return out

"""Pivot / group-by aggregator for `TableModel`.

Two modes:
  - **Group-by** (no `col` axis): output is a 2-column table, rows
    keyed by the unique values of `row_col`, values aggregated from
    `value_col` per group.
  - **Pivot** (`col_col` set): output is a 2-D table of
    rows × unique-`col_col`-values, cells = aggregate of `value_col`
    in each (row_key, col_key) bucket.

Honours the active filter — only visible rows feed the aggregator.
Non-numeric values silently drop. `count` works on any column type.

Aggregators: sum / mean / count / min / max / median.
"""
from __future__ import annotations
from collections import defaultdict
from statistics import median as _median

from .table_model import to_number


def _safe_min(vs): return min(vs) if vs else 0
def _safe_max(vs): return max(vs) if vs else 0
def _safe_mean(vs): return sum(vs) / len(vs) if vs else 0
def _safe_median(vs): return _median(vs) if vs else 0

AGGS: dict[str, callable] = {
    "sum":    sum,
    "mean":   _safe_mean,
    "count":  len,
    "min":    _safe_min,
    "max":    _safe_max,
    "median": _safe_median,
}


def pivot(model, row_col: int, value_col: int,
          agg: str = "sum",
          col_col: int | None = None) -> tuple[list[str], list[list[str]]]:
    """Return `(header, rows)` for the pivoted result.

    `row_col`, `value_col`, `col_col` are 0-based column indices into
    `model`. `agg` must be a key of `AGGS`. Caller is responsible for
    feeding numeric `value_col`s when the agg requires them (`count`
    is the only one that doesn't).
    """
    if agg not in AGGS:
        raise ValueError(
            f"unknown aggregator {agg!r}; use one of {sorted(AGGS)}")
    n = model.rowCount()
    headers = model.header()
    if not (0 <= row_col < len(headers) and 0 <= value_col < len(headers)):
        raise ValueError("row_col / value_col out of range")
    fn = AGGS[agg]

    def num(s):
        v = to_number(s)
        return v if v is not None else None

    if col_col is None:
        groups: dict[str, list[float]] = defaultdict(list)
        for r in range(n):
            key = model.get_value(r, row_col)
            if agg == "count":
                groups[key].append(1)
            else:
                v = num(model.get_value(r, value_col))
                if v is not None:
                    groups[key].append(v)
        header = [headers[row_col], f"{agg}({headers[value_col]})"]
        rows = [[k, _fmt(fn(vs))] for k, vs in sorted(groups.items())]
        return header, rows

    if not (0 <= col_col < len(headers)):
        raise ValueError("col_col out of range")
    cells: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    col_keys: set[str] = set()
    for r in range(n):
        rk = model.get_value(r, row_col)
        ck = model.get_value(r, col_col)
        col_keys.add(ck)
        if agg == "count":
            cells[rk][ck].append(1)
        else:
            v = num(model.get_value(r, value_col))
            if v is not None:
                cells[rk][ck].append(v)
    sorted_cols = sorted(col_keys)
    header = [headers[row_col]] + sorted_cols
    rows = []
    for rk in sorted(cells.keys()):
        row = [rk]
        for ck in sorted_cols:
            vs = cells[rk].get(ck, [])
            row.append(_fmt(fn(vs)) if vs else "")
        rows.append(row)
    return header, rows


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def to_csv(header: list[str], rows: list[list[str]]) -> str:
    """Serialize a pivot result back to CSV text. Used to round-trip
    the result into a new tab via `api.open(path)`."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()

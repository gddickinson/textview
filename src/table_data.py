"""Qt-free table helpers shared by the table view, stats dialog and the
web interface.

- `parse_delimited(text, delimiter=None)` — csv.Sniffer-based split into
  `(header, rows, delimiter)`.
- `is_numeric(s)` / `to_number(s)` — cell classification and parsing.
- `detect_numeric_columns(header, rows)` — which columns hold numbers
  (sampled from the first 64 rows).
- `numeric_stats(values)` / `string_stats(values)` — one row of the
  per-column statistics grid (Table → Column statistics).

`table_model` and `stats_dialog` import these back, so behaviour is shared.
"""
import csv
import io
import re
from collections import Counter
from statistics import mean, median, pstdev, quantiles
import math


_NUMERIC_RE = re.compile(r"""^\s*-?(?:\d{1,3}(?:[,_]\d{3})+|\d+)(?:\.\d+)?\s*%?\s*$""")
_SAMPLE_BYTES = 4096
_NUMERIC_SAMPLE_ROWS = 64


def parse_delimited(text: str, delimiter: str | None = None,
                    has_header: bool = True):
    """Split delimited text into (header, rows, delimiter).

    If `delimiter` is None or empty, sniff it. Falls back to comma when the
    sniffer is unhappy with the sample (e.g. a single-column file).
    """
    sample = text[:_SAMPLE_BYTES]
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if r]   # drop blank lines
    if not rows:
        return [], [], delimiter
    if has_header:
        header = rows[0]
        body = rows[1:]
    else:
        n = max(len(r) for r in rows)
        header = [f"col {i + 1}" for i in range(n)]
        body = rows
    width = len(header)
    body = [
        r + [""] * (width - len(r)) if len(r) < width else r[:width]
        for r in body
    ]
    return header, body, delimiter


def is_numeric(s: str) -> bool:
    return bool(_NUMERIC_RE.match(s or ""))


def to_number(s: str):
    """Best-effort string→float. Strips commas, underscores, %; returns
    None on failure."""
    if s is None:
        return None
    t = str(s).strip().rstrip("%").replace(",", "").replace("_", "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def detect_numeric_columns(header, rows):
    """Per column: True when every non-empty cell in the first
    `_NUMERIC_SAMPLE_ROWS` rows is numeric."""
    cols = []
    sample = rows[:_NUMERIC_SAMPLE_ROWS]
    for i in range(len(header)):
        non_empty = [r[i] for r in sample if i < len(r) and r[i].strip()]
        if not non_empty:
            cols.append(False)
            continue
        cols.append(all(is_numeric(v) for v in non_empty))
    return cols


_NUMERIC_COLS = [
    "count", "missing", "mean", "median", "stddev",
    "min", "Q1", "Q3", "max", "range", "skew", "kurt",
]
_STRING_COLS = ["count", "missing", "unique", "top", "top_freq"]


def numeric_stats(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {k: "" for k in _NUMERIC_COLS}
    m = mean(values)
    sd = pstdev(values) if n > 1 else 0.0
    if n >= 4:
        q = quantiles(values, n=4)  # [Q1, Q2, Q3]
        q1, q3 = q[0], q[2]
    else:
        q1 = q3 = ""
    # Population skew + kurtosis (Fisher's). Fall back to "" when sd is 0.
    if sd > 0 and n > 2:
        skew = sum((v - m) ** 3 for v in values) / (n * sd ** 3)
        kurt = sum((v - m) ** 4 for v in values) / (n * sd ** 4) - 3.0
    else:
        skew = kurt = ""

    def fmt(x):
        if x == "" or x is None:
            return ""
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return ""
        return f"{x:.4g}"

    return {
        "count": str(n), "mean": fmt(m), "median": fmt(median(values)),
        "stddev": fmt(sd), "min": fmt(min(values)), "max": fmt(max(values)),
        "Q1": fmt(q1), "Q3": fmt(q3),
        "range": fmt(max(values) - min(values)),
        "skew": fmt(skew), "kurt": fmt(kurt),
    }


def string_stats(values: list[str]) -> dict:
    counts = Counter(v for v in values if v != "")
    n = len(values)
    if not counts:
        return {"count": str(n), "unique": "0", "top": "", "top_freq": ""}
    top, top_freq = counts.most_common(1)[0]
    return {
        "count": str(n), "unique": str(len(counts)),
        "top": str(top)[:40], "top_freq": str(top_freq),
    }

"""Module-control tools — thin wrappers over `AppAPI`.

These let the LLM drive every module the user can: open files, switch
tabs, move the cursor, apply table filter / sort, and produce charts.
None of them touch disk or run code, so they live in `READ_ONLY_TOOLS`.
File I/O, command execution, and setting changes stay in `ACTION_TOOLS`
(see `tools.py`) where the agent's confirmation flow gates them.
"""
from .tools_base import Tool


def _list_tabs(window):
    api = window.api
    paths = api.tabs() or ["(none)"]
    return f"active: {api.active_tab()}\n" + "\n".join(
        f"{i}: {p}" for i, p in enumerate(paths))


def _switch_tab(window, index: int):
    api = window.api
    n = len(api.tabs())
    if not 0 <= int(index) < n:
        return f"error: index {index} out of range (0..{n - 1})."
    api.switch_tab(int(index))
    return f"switched to tab {index}"


def _goto_line(window, line: int):
    window.api.goto_line(int(line))
    return f"cursor on line {line}"


def _table_summary(window):
    api = window.api
    if api.current_format() != "csv":
        return "error: no CSV / table currently open."
    m = api.table_model()
    if m is None:
        return "error: no table model."
    return (
        f"header: {api.table_header()}\n"
        f"visible rows: {m.rowCount()} of {m.total_rows()}\n"
        f"numeric columns: "
        f"{[h for h, n in zip(api.table_header(), m.numeric_columns()) if n]}\n"
        f"sort: {m._sort}  filter: {m._filter}"
    )


def _apply_table_filter(window, column: str, op: str, value: str):
    if window.api.current_format() != "csv":
        return "error: no table open."
    window.api.table_set_filter(column, op, str(value))
    m = window.api.table_model()
    return (f"filter {column} {op} {value!r} → "
            f"{m.rowCount()} of {m.total_rows()} rows")


def _clear_table_filter(window):
    if window.api.current_format() != "csv":
        return "error: no table open."
    window.api.table_clear_filter()
    return "filter cleared"


def _sort_table(window, column: str, ascending: bool = True):
    if window.api.current_format() != "csv":
        return "error: no table open."
    window.api.table_sort(column, ascending=ascending)
    return f"sorted {column} {'asc' if ascending else 'desc'}"


def _make_chart(window, kind: str, x: str | None = None,
                y: list[str] | None = None,
                save_path: str | None = None,
                title: str = ""):
    if window.api.current_format() != "csv":
        return "error: no table open."
    window.api.table_plot(kind=kind, x=x, y=y, title=title, save=save_path)
    return f"chart '{kind}' rendered" + (
        f" → {save_path}" if save_path else "")


def _compute_stats(window, column: str | None = None):
    """Return descriptive statistics for one column, or for all numeric
    columns when `column` is omitted. Filtered rows are excluded
    (matches the StatsDialog behaviour)."""
    if window.api.current_format() != "csv":
        return "error: no table open."
    from ..stats_dialog import column_stats
    m = window.api.table_model()
    if m is None:
        return "error: no table model."
    header = m.header()
    if column is not None:
        if column not in header:
            return f"error: column '{column}' not found. Available: {header}"
        s = column_stats(m, header.index(column))
        return _format_stats_row(column, s)
    # All columns
    rows = []
    for i, name in enumerate(header):
        s = column_stats(m, i)
        rows.append(_format_stats_row(name, s))
    return "\n".join(rows)


def _format_stats_row(name: str, s: dict) -> str:
    """Compact one-line formatting suitable for a tool_result string."""
    if s.get("__numeric__"):
        bits = [f"count={s.get('count')}", f"missing={s.get('__missing__')}"]
        for k in ("mean", "median", "stddev", "min", "max",
                  "Q1", "Q3", "range", "skew", "kurt"):
            v = s.get(k, "")
            if v != "":
                bits.append(f"{k}={v}")
        return f"{name} (numeric): " + " ".join(bits)
    bits = [f"count={s.get('count')}", f"missing={s.get('__missing__')}",
            f"unique={s.get('unique')}",
            f"top={s.get('top')!r}({s.get('top_freq')})"]
    return f"{name} (text): " + " ".join(bits)


def _add_derived_column(window, name: str, formula: str):
    if window.api.current_format() != "csv":
        return "error: no table open."
    m = window.api.table_model()
    if m is None:
        return "error: no table model."
    ok, msg = m.add_derived_column(name, formula)
    return msg if ok else f"error: {msg}"


def _pivot_table(window, rows: str, values: str, agg: str = "sum",
                 cols: str | None = None, save_path: str | None = None):
    if window.api.current_format() != "csv":
        return "error: no table open."
    m = window.api.table_model()
    if m is None:
        return "error: no table model."
    headers = m.header()
    try:
        row_idx = headers.index(rows)
        val_idx = headers.index(values)
    except ValueError:
        return f"error: column not found. Available: {headers}"
    col_idx = headers.index(cols) if cols and cols in headers else None
    from ..table_pivot import pivot, to_csv
    try:
        h, rs = pivot(m, row_idx, val_idx, agg, col_idx)
    except ValueError as e:
        return f"error: {e}"
    from pathlib import Path
    import tempfile
    if save_path:
        Path(save_path).write_text(to_csv(h, rs), encoding="utf-8")
        msg = f"saved {len(rs)}-row pivot → {save_path}"
    else:
        out = Path(tempfile.gettempdir()) / "textview_pivots" / f"pivot_{rows}_{agg}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_csv(h, rs), encoding="utf-8")
        window.api.open(str(out))
        msg = f"opened pivot ({len(rs)} rows × {len(h)} cols) in new tab"
    # Always include a small text preview so the agent sees what came out
    preview = "\n".join("\t".join(r) for r in [h] + rs[:10])
    return f"{msg}\n\n{preview}" + ("\n…[truncated]" if len(rs) > 10 else "")


def _correlation_matrix(window):
    """Return the pairwise Pearson correlation matrix as a labelled
    table (one line per column pair). Filter-aware."""
    if window.api.current_format() != "csv":
        return "error: no table open."
    import numpy as np
    m = window.api.table_model()
    if m is None:
        return "error: no table model."
    header = m.header()
    nums = m.numeric_columns()
    cols = [i for i, n in enumerate(nums) if n]
    if len(cols) < 2:
        return "error: need ≥ 2 numeric columns."
    from ..table_model import to_number
    data = []
    for ci in cols:
        col = []
        for r in range(m.rowCount()):
            v = to_number(m.get_value(r, ci))
            col.append(float("nan") if v is None else v)
        data.append(col)
    arr = np.array(data)
    masked = np.ma.masked_invalid(arr)
    corr = np.ma.corrcoef(masked).filled(float("nan"))
    names = [header[i] for i in cols]
    out = []
    for i, ni in enumerate(names):
        for j, nj in enumerate(names):
            if j > i:
                v = corr[i, j]
                out.append(f"  {ni:>10} ↔ {nj:<10}  r = {v:+.3f}")
    return "Pairwise Pearson correlation:\n" + "\n".join(out)


MODULE_TOOLS: list[Tool] = [
    Tool(
        name="list_tabs",
        description="List the open tabs (file paths) and the active index.",
        input_schema={"type": "object", "properties": {}},
        call=_list_tabs,
    ),
    Tool(
        name="switch_tab",
        description="Switch to the tab at the given 0-based index.",
        input_schema={
            "type": "object",
            "properties": {"index": {"type": "integer"}},
            "required": ["index"],
        },
        call=_switch_tab,
    ),
    Tool(
        name="goto_line",
        description="Move the editor's cursor to a 1-based line number.",
        input_schema={
            "type": "object",
            "properties": {"line": {"type": "integer"}},
            "required": ["line"],
        },
        call=_goto_line,
    ),
    Tool(
        name="table_summary",
        description="Get header, row counts, numeric-column list, and current "
                    "sort/filter state for the open CSV / TSV table.",
        input_schema={"type": "object", "properties": {}},
        call=_table_summary,
    ),
    Tool(
        name="apply_table_filter",
        description="Filter the table to rows where COLUMN OP VALUE. OP is one "
                    "of '~' (substring), '>', '>=', '<', '<=', '=', '!='.",
        input_schema={
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "op": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["column", "op", "value"],
        },
        call=_apply_table_filter,
    ),
    Tool(
        name="clear_table_filter",
        description="Remove any active filter on the current table.",
        input_schema={"type": "object", "properties": {}},
        call=_clear_table_filter,
    ),
    Tool(
        name="sort_table",
        description="Sort the current table by COLUMN, ascending or descending. "
                    "Numeric columns sort numerically.",
        input_schema={
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "ascending": {"type": "boolean", "default": True},
            },
            "required": ["column"],
        },
        call=_sort_table,
    ),
    Tool(
        name="make_chart",
        description="Render a chart from the current (visible) table data. "
                    "kind: Line | Bar | Scatter | Histogram | Pie | Box | "
                    "Heatmap | Correlation matrix. If save_path is given, "
                    "the chart is saved without showing the dialog.",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "x": {"type": "string"},
                "y": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
                "save_path": {"type": "string"},
            },
            "required": ["kind"],
        },
        call=_make_chart,
    ),
    Tool(
        name="compute_stats",
        description="Compute descriptive statistics (count / missing / mean / "
                    "median / stddev / min / max / Q1 / Q3 / range / skew / "
                    "kurtosis for numeric columns; count / unique / top for "
                    "text columns). Pass `column` to limit to one column, "
                    "or omit for all. Honours the active filter.",
        input_schema={
            "type": "object",
            "properties": {"column": {"type": "string"}},
        },
        call=_compute_stats,
    ),
    Tool(
        name="add_derived_column",
        description="Add a new column whose value is computed per-row from "
                    "`formula` (a Python expression). Other columns are bound "
                    "as variables (numeric → float, text → str). Math "
                    "functions log / sqrt / exp / abs / min / max / round are "
                    "available. Example formulas: 'age * 2', 'score / 100', "
                    "'log(income)'.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "formula": {"type": "string"},
            },
            "required": ["name", "formula"],
        },
        call=_add_derived_column,
    ),
    Tool(
        name="correlation_matrix",
        description="Return the pairwise Pearson correlation matrix for the "
                    "numeric columns of the visible (filtered) data, "
                    "formatted as one line per column pair.",
        input_schema={"type": "object", "properties": {}},
        call=_correlation_matrix,
    ),
    Tool(
        name="pivot_table",
        description="Group-by or pivot the open table. With only `rows` + "
                    "`values`, computes a 2-column groupby. Adding `cols` "
                    "produces a 2-D pivot. `agg` is one of sum / mean / "
                    "count / min / max / median. Result opens in a new "
                    "tab unless `save_path` is given. A preview of the "
                    "first 10 rows is included in the response.",
        input_schema={
            "type": "object",
            "properties": {
                "rows":      {"type": "string"},
                "values":    {"type": "string"},
                "agg":       {"type": "string", "default": "sum"},
                "cols":      {"type": "string"},
                "save_path": {"type": "string"},
            },
            "required": ["rows", "values"],
        },
        call=_pivot_table,
    ),
]

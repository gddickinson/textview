"""Data model for the spreadsheet view.

`parse_delimited(text, delimiter=None)` uses Python's `csv.Sniffer` to guess
the delimiter from the first 4 KB if one isn't supplied. Returns
`(header, rows, delimiter_used)`.

`TableModel` is a `QAbstractTableModel`:
  - Detects which columns hold numbers (sampled from the first 64 rows) so
    we can right-align them and sort numerically rather than lexically.
  - Supports in-place sort (`sort()` swaps row order; resetting the model
    is faster than wiring a `QSortFilterProxyModel` for our scale).
  - Optionally editable via `set_editable(True)` — `setData` writes back to
    the row buffer; `serialize(delimiter)` round-trips to CSV text.
"""
import csv
import io
import math
import re

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex

# Qt-free parsing / classification helpers (re-exported for existing callers).
from .table_data import (  # noqa: F401
    _NUMERIC_RE, _SAMPLE_BYTES, _NUMERIC_SAMPLE_ROWS,
    parse_delimited, is_numeric, to_number, detect_numeric_columns,
)


# Whitelisted functions exposed to derived-column formulas. Plain math
# only; no IO, no introspection. The `__builtins__` slot is set to a
# minimal dict explicitly so lookups like `__import__` are unavailable.
_FORMULA_GLOBALS = {
    "__builtins__": {
        "abs": abs, "min": min, "max": max, "round": round,
        "len": len, "sum": sum, "int": int, "float": float, "str": str,
        "True": True, "False": False, "None": None,
    },
    **{name: getattr(math, name) for name in (
        "log", "log2", "log10", "exp", "sqrt", "pow",
        "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "floor", "ceil", "pi", "e", "tau", "isnan", "isinf",
    )},
}


class TableModel(QAbstractTableModel):
    """Column-major view over `(header, rows)`."""

    def __init__(self, header, rows, parent=None):
        super().__init__(parent)
        self._header = list(header)
        self._rows = [list(r) for r in rows]
        self._editable = False
        self._numeric_columns = self._detect_numeric_columns()
        # `_visible` maps view-row → underlying-row index in `_rows`. Filtering
        # only mutates this list; sorting reorders it. The underlying data is
        # never lost, so clearing the filter restores everything.
        self._visible: list[int] = list(range(len(self._rows)))
        self._filter: tuple | None = None  # (col_idx, op, value) or None
        self._sort: tuple | None = None    # (col, order) — last sort applied

    def _detect_numeric_columns(self):
        return detect_numeric_columns(self._header, self._rows)

    # -- Qt model API --------------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._header)

    def _underlying(self, view_row: int) -> int | None:
        if 0 <= view_row < len(self._visible):
            return self._visible[view_row]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        u = self._underlying(index.row())
        c = index.column()
        if u is None or c >= len(self._header):
            return None
        row = self._rows[u]
        val = row[c] if c < len(row) else ""
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return val
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if self._numeric_columns[c]:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation,
                   role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._header):
                return self._header[section]
            return None
        # Vertical header shows the underlying row number so the user can
        # tell that row N (filtered) was originally row M in the file.
        u = self._underlying(section)
        return str((u if u is not None else section) + 1)

    def flags(self, index):
        f = super().flags(index)
        if self._editable and index.isValid():
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        u = self._underlying(index.row())
        c = index.column()
        if u is None or c >= len(self._header):
            return False
        row = self._rows[u]
        while len(row) < len(self._header):
            row.append("")
        row[c] = "" if value is None else str(value)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self._header):
            return
        self._sort = (column, order)
        self.beginResetModel()
        try:
            # PyQt6 6.7+ enums are strict — they aren't int subclasses and
            # `int(SortOrder)` raises TypeError. Pull `.value` for enums,
            # use the int directly otherwise. So callers passing raw ints
            # (external control, JSON bridges) get the expected behavior.
            ord_v = order.value if hasattr(order, "value") else order
            reverse = ord_v == 1  # Qt.SortOrder.DescendingOrder.value == 1
            rows = self._rows
            if self._numeric_columns[column]:
                def keyfn(u):
                    row = rows[u]
                    if column >= len(row):
                        return float("-inf")
                    n = to_number(row[column])
                    return n if n is not None else float("-inf")
            else:
                def keyfn(u):
                    row = rows[u]
                    return row[column].lower() if column < len(row) else ""
            self._visible.sort(key=keyfn, reverse=reverse)
        finally:
            self.endResetModel()

    # -- accessors / mutators -----------------------------------------------

    def set_editable(self, on: bool):
        # Don't reset the model — the change in flags() takes effect when
        # the next edit interaction queries them, no need to invalidate
        # cell visuals.
        self._editable = on

    def serialize(self, delimiter: str = ",") -> str:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=delimiter)
        w.writerow(self._header)
        for row in self._rows:
            w.writerow(row)
        return buf.getvalue()

    def get_value(self, row: int, col: int) -> str:
        u = self._underlying(row)
        if u is None or not 0 <= col < len(self._header):
            return ""
        r = self._rows[u]
        return r[col] if col < len(r) else ""

    def numeric_columns(self):
        return list(self._numeric_columns)

    def header(self):
        return list(self._header)

    # -- filtering ----------------------------------------------------------

    def set_filter(self, col: int, op: str, value: str):
        """Restrict visible rows to those matching `<col> <op> <value>`.

        Operators: `~` (case-insensitive substring), `>`, `>=`, `<`, `<=`,
        `=`/`==`, `!=`. Numeric comparisons are used when the column was
        flagged numeric; otherwise string lower-case compare. An invalid
        / unparseable row is excluded (not preserved silently)."""
        if col < 0 or col >= len(self._header):
            return
        self._filter = (col, op, value)
        self._apply_filter()

    def clear_filter(self):
        self._filter = None
        self._apply_filter()

    def has_filter(self) -> bool:
        return self._filter is not None

    def total_rows(self) -> int:
        return len(self._rows)

    def _apply_filter(self):
        self.beginResetModel()
        try:
            if self._filter is None:
                self._visible = list(range(len(self._rows)))
                return
            col, op, value = self._filter
            is_num = self._numeric_columns[col]
            ref_num = to_number(value) if is_num else None
            ref_str = (value or "").lower()
            out = []
            for i, row in enumerate(self._rows):
                cell = row[col] if col < len(row) else ""
                if op == "~":
                    if ref_str in (cell or "").lower():
                        out.append(i)
                    continue
                if is_num:
                    if ref_num is None:
                        continue
                    n = to_number(cell)
                    if n is None:
                        continue
                    a, b = n, ref_num
                else:
                    a, b = (cell or "").lower(), ref_str
                if   op == ">"            and a >  b: out.append(i)
                elif op == ">="           and a >= b: out.append(i)
                elif op == "<"            and a <  b: out.append(i)
                elif op == "<="           and a <= b: out.append(i)
                elif op in ("=", "==")    and a == b: out.append(i)
                elif op == "!="           and a != b: out.append(i)
            self._visible = out
        finally:
            self.endResetModel()

    # -- structural mutations -----------------------------------------------

    def insert_row(self, values: list[str] | None = None,
                   after_view_row: int | None = None):
        """Append a row to the underlying buffer. `after_view_row` is
        ignored when filter / sort is active — the row goes to the end of
        the natural order, and the filter / sort are re-applied."""
        width = len(self._header) or 1
        new_row = list(values) if values else [""] * width
        while len(new_row) < width:
            new_row.append("")
        new_row = new_row[:width]
        self._rows.append(new_row)
        # If the user asked to insert after a specific view row and there's
        # no sort/filter, splice into the underlying list at that position
        # so the natural order matches expectation.
        if after_view_row is not None and self._sort is None and self._filter is None:
            target_underlying = self._underlying(after_view_row)
            if target_underlying is not None:
                self._rows.pop()    # undo the append
                self._rows.insert(target_underlying + 1, new_row)
        self._numeric_columns = self._detect_numeric_columns()
        self._apply_filter()
        if self._sort is not None:
            self.sort(*self._sort)

    def delete_rows(self, view_rows: list[int]):
        """Drop the rows at the given view positions (1-by-1, deduped)."""
        underlying = sorted(
            {self._underlying(r) for r in view_rows
             if self._underlying(r) is not None},
            reverse=True,
        )
        if not underlying:
            return
        for u in underlying:
            del self._rows[u]
        self._numeric_columns = self._detect_numeric_columns()
        self._apply_filter()
        if self._sort is not None:
            self.sort(*self._sort)

    def add_derived_column(self, name: str, formula: str) -> tuple[bool, str]:
        """Compute a new column from `formula`, evaluated per row.

        Numeric column values become local variables (where the column
        name is a valid Python identifier); string column values are
        bound as strings. Math functions (`log`, `sqrt`, `exp`, …) and
        a few stdlib helpers (`abs`, `min`, `max`, `round`) are in
        scope. Invalid rows produce empty cells, not exceptions.

        Returns `(ok, message)` — ok=False if compilation failed (e.g.
        SyntaxError).
        """
        if not name.strip():
            return False, "Column name is empty."
        try:
            code = compile(formula, "<formula>", "eval")
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg}"

        nums = self._numeric_columns
        results: list[str] = []
        any_numeric = False
        for row in self._rows:
            ns: dict = {}
            for i, hdr in enumerate(self._header):
                if not hdr.isidentifier():
                    continue
                if i >= len(row):
                    continue
                if nums[i]:
                    ns[hdr] = to_number(row[i]) or 0.0
                else:
                    ns[hdr] = row[i]
            try:
                val = eval(code, _FORMULA_GLOBALS, ns)
            except Exception:
                results.append("")
                continue
            if isinstance(val, float):
                if math.isnan(val) or math.isinf(val):
                    results.append("")
                else:
                    results.append(f"{val:g}")
                    any_numeric = True
            elif isinstance(val, bool):
                results.append("True" if val else "False")
            elif isinstance(val, (int,)):
                results.append(str(val))
                any_numeric = True
            else:
                results.append(str(val))

        n_populated = sum(1 for r in results if r)
        if n_populated == 0:
            return False, ("Formula evaluated to empty for every row. "
                           "Common causes: misspelled column name (variable "
                           "must be a Python identifier), use of an unbound "
                           "function, or division by zero everywhere.")
        self.beginResetModel()
        try:
            self._header.append(name)
            for row, v in zip(self._rows, results):
                row.append(v)
            self._numeric_columns = self._detect_numeric_columns()
        finally:
            self.endResetModel()
        self._apply_filter()
        if self._sort is not None:
            self.sort(*self._sort)
        return True, f"Added '{name}' ({n_populated} populated)"

    def insert_column(self, at: int = -1, name: str = "new"):
        """Insert a blank column at `at` (default = end)."""
        if at < 0 or at > len(self._header):
            at = len(self._header)
        self.beginResetModel()
        try:
            self._header.insert(at, name)
            for row in self._rows:
                row.insert(min(at, len(row)), "")
            self._numeric_columns = self._detect_numeric_columns()
        finally:
            self.endResetModel()
        # Reapply filter (column indices may have shifted).
        self._apply_filter()
        if self._sort is not None:
            self.sort(*self._sort)

    def delete_columns(self, cols: list[int]):
        cols = sorted({c for c in cols if 0 <= c < len(self._header)},
                      reverse=True)
        if not cols:
            return
        self.beginResetModel()
        try:
            for c in cols:
                del self._header[c]
                for row in self._rows:
                    if c < len(row):
                        del row[c]
            self._numeric_columns = self._detect_numeric_columns()
        finally:
            self.endResetModel()
        self._apply_filter()
        # Sort column may have been removed; only resort if still in range.
        if self._sort is not None and self._sort[0] < len(self._header):
            self.sort(*self._sort)
        else:
            self._sort = None

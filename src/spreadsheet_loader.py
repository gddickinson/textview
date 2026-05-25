"""Read Excel (`.xlsx` / `.xlsm` / `.xltx` / `.xltm`) and OpenDocument
(`.ods`) spreadsheets, then surface them through the existing CSV /
TableView pipeline.

Strategy: extract one sheet's rows to a CSV-shaped string. `TableModel`
already infers numeric columns from the textual representation, so
nothing else needs to know the file came from a workbook.

Multi-sheet files: `list_sheets(path)` returns sheet names in workbook
order; `load_sheet_as_csv(path, sheet)` takes either a name or a
0-based index. `MainWindow` exposes a **Table → Switch sheet…** action
that re-routes through `load_sheet_as_csv` to swap sheets without
reopening the file.

The XLSX read uses `openpyxl` (in requirements). ODS uses `pandas`
+ `odfpy` if installed; otherwise raises `SpreadsheetReadError` with
a friendly install hint. Always lazy-imported so a missing optional
dep doesn't break startup.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path


XLSX_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
ODS_EXTENSIONS = {".ods"}
LEGACY_XLS_EXTENSIONS = {".xls"}
ALL_EXTENSIONS = XLSX_EXTENSIONS | ODS_EXTENSIONS | LEGACY_XLS_EXTENSIONS


class SpreadsheetReadError(Exception):
    """Raised when a spreadsheet can't be opened (missing dep, parse error)."""


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in ALL_EXTENSIONS


def list_sheets(path: str) -> list[str]:
    """Return sheet names in workbook order. Raises `SpreadsheetReadError`
    when the file can't be read at all (missing dep, corrupt file)."""
    ext = Path(path).suffix.lower()
    if ext in XLSX_EXTENSIONS:
        return _xlsx_list_sheets(path)
    if ext in ODS_EXTENSIONS:
        return _ods_list_sheets(path)
    if ext in LEGACY_XLS_EXTENSIONS:
        return _xls_list_sheets(path)
    raise SpreadsheetReadError(f"Unsupported spreadsheet extension: {ext}")


def load_sheet_as_csv(path: str, sheet: str | int = 0) -> str:
    """Extract one sheet to CSV text. `sheet` is either a sheet name
    (str) or a 0-based index (int). Empty sheets return an empty string."""
    ext = Path(path).suffix.lower()
    if ext in XLSX_EXTENSIONS:
        return _xlsx_sheet_to_csv(path, sheet)
    if ext in ODS_EXTENSIONS:
        return _ods_sheet_to_csv(path, sheet)
    if ext in LEGACY_XLS_EXTENSIONS:
        return _xls_sheet_to_csv(path, sheet)
    raise SpreadsheetReadError(f"Unsupported spreadsheet extension: {ext}")


# ------------------------------------------------------------- XLSX (openpyxl) --

def _xlsx_workbook(path: str):
    try:
        import openpyxl  # type: ignore
    except ImportError as e:
        raise SpreadsheetReadError(
            "openpyxl is required to read Excel files. "
            "Install with `pip install openpyxl`."
        ) from e
    try:
        # data_only=True so formulas appear as their last cached result
        # rather than `=SUM(A1:A10)`.
        return openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        raise SpreadsheetReadError(f"Could not open Excel file: {e}") from e


def _xlsx_list_sheets(path: str) -> list[str]:
    wb = _xlsx_workbook(path)
    try:
        return list(wb.sheetnames)
    finally:
        try: wb.close()
        except Exception: pass


def _xlsx_sheet_to_csv(path: str, sheet: str | int) -> str:
    wb = _xlsx_workbook(path)
    try:
        names = wb.sheetnames
        if not names:
            return ""
        if isinstance(sheet, int):
            if not 0 <= sheet < len(names):
                raise SpreadsheetReadError(
                    f"Sheet index {sheet} out of range (0..{len(names) - 1}).")
            ws = wb[names[sheet]]
        else:
            if sheet not in names:
                raise SpreadsheetReadError(
                    f"No such sheet: {sheet!r}. Available: {names}")
            ws = wb[sheet]
        return _rows_iter_to_csv(ws.iter_rows(values_only=True))
    finally:
        try: wb.close()
        except Exception: pass


# ---------------------------------------------------------- ODS (pandas+odfpy) --

def _ods_engine():
    """Lazy ODS reader. pandas + odfpy is the common combo; we try both."""
    try:
        import pandas as pd  # type: ignore
        import odf  # type: ignore  # noqa: F401
    except ImportError as e:
        raise SpreadsheetReadError(
            "Reading .ods needs `pandas` + `odfpy`. Install with "
            "`pip install pandas odfpy`."
        ) from e
    return pd


def _ods_list_sheets(path: str) -> list[str]:
    pd = _ods_engine()
    try:
        with pd.ExcelFile(path, engine="odf") as xf:
            return list(xf.sheet_names)
    except Exception as e:
        raise SpreadsheetReadError(f"Could not open ODS file: {e}") from e


def _ods_sheet_to_csv(path: str, sheet: str | int) -> str:
    pd = _ods_engine()
    try:
        df = pd.read_excel(path, engine="odf", sheet_name=sheet, header=None)
    except Exception as e:
        raise SpreadsheetReadError(f"Could not read ODS sheet: {e}") from e
    return _dataframe_to_csv(df)


# ------------------------------------------------------------ legacy XLS (xlrd) --

def _xls_engine():
    try:
        import xlrd  # type: ignore
    except ImportError as e:
        raise SpreadsheetReadError(
            "Reading legacy .xls files needs `xlrd`. Install with "
            "`pip install xlrd`."
        ) from e
    return xlrd


def _xls_list_sheets(path: str) -> list[str]:
    xlrd = _xls_engine()
    try:
        wb = xlrd.open_workbook(path)
        return list(wb.sheet_names())
    except Exception as e:
        raise SpreadsheetReadError(f"Could not open .xls file: {e}") from e


def _xls_sheet_to_csv(path: str, sheet: str | int) -> str:
    xlrd = _xls_engine()
    try:
        wb = xlrd.open_workbook(path)
        if isinstance(sheet, int):
            ws = wb.sheet_by_index(sheet)
        else:
            ws = wb.sheet_by_name(sheet)
        rows = (tuple(ws.cell_value(r, c) for c in range(ws.ncols))
                for r in range(ws.nrows))
        return _rows_iter_to_csv(rows)
    except Exception as e:
        raise SpreadsheetReadError(f"Could not read .xls sheet: {e}") from e


# --------------------------------------------------------------- helpers --

def _format_cell(v) -> str:
    """Stringify a cell value while preserving int-ness (so 10 stays '10'
    not '10.0' when openpyxl gives us a float for an integer cell)."""
    if v is None: return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _rows_iter_to_csv(rows_iter) -> str:
    """Serialize an iterator of tuples to CSV text, trimming trailing
    empty cells per row and trailing all-empty rows at the very end."""
    out = io.StringIO()
    writer = csv.writer(out)
    written = 0
    # Buffer one row at a time so we can drop trailing empty rows.
    buffered_empty: list[list[str]] = []
    for row in rows_iter:
        cells = [_format_cell(c) for c in row]
        # Strip trailing empty cells.
        while cells and cells[-1] == "":
            cells.pop()
        if not cells:
            buffered_empty.append([])
            continue
        # Flush any deferred empty rows that are now between content.
        for empty in buffered_empty:
            writer.writerow(empty); written += 1
        buffered_empty.clear()
        writer.writerow(cells); written += 1
    return out.getvalue()


def _dataframe_to_csv(df) -> str:
    """pandas DataFrame → CSV text. Uses the same int-preserving rule
    as `_format_cell` by going through the row iterator."""
    return _rows_iter_to_csv(df.itertuples(index=False, name=None))


# --------------------------------------------------- MainWindow glue --

def show_sheet_picker(window) -> None:
    """**Table → Switch sheet…** action handler. Shows an input dialog
    listing the sheets in the active workbook, reloads the chosen sheet
    into the table view. No-op when the active file isn't a workbook."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "xlsx" or not window._current_path:
        window.statusBar().showMessage("Switch sheet: no workbook is open.", 5000)
        return
    sheets = getattr(window, "_xlsx_sheets", []) or []
    if len(sheets) <= 1:
        window.statusBar().showMessage(
            "This workbook has only one sheet.", 4000)
        return
    current = getattr(window, "_xlsx_sheet_index", 0)
    name, ok = QInputDialog.getItem(
        window, "Switch sheet",
        f"Sheets in {Path(window._current_path).name}:",
        sheets, current, False,
    )
    if not ok: return
    idx = sheets.index(name)
    if idx == current: return
    try:
        csv_text = load_sheet_as_csv(window._current_path, idx)
    except SpreadsheetReadError as e:
        QMessageBox.warning(window, "Could not switch sheet", str(e))
        return
    window._xlsx_sheet_index = idx
    window._current_content = csv_text
    window._table_source = None  # force re-parse
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    window.statusBar().showMessage(
        f"Loaded sheet {idx + 1}/{len(sheets)}: {name!r}", 4000)

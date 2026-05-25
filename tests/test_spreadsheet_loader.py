"""Coverage for src.spreadsheet_loader — XLSX round-trip + error paths.

`.xls` / `.ods` tests are wrapped in `pytest.skipif` so the suite stays
green when those optional readers (`xlrd` / `pandas`+`odfpy`) aren't
installed.
"""
from __future__ import annotations

import importlib
import pytest
from pathlib import Path

from src.spreadsheet_loader import (
    list_sheets, load_sheet_as_csv, is_supported, SpreadsheetReadError,
    XLSX_EXTENSIONS, ODS_EXTENSIONS, LEGACY_XLS_EXTENSIONS,
)


def _have(modules):
    for m in modules:
        try: importlib.import_module(m)
        except Exception: return False
    return True


@pytest.fixture
def two_sheet_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Numbers"
    ws.append(["a", "b", "c"])
    ws.append([1, 2, 3.5])
    ws.append([4, 5, 6.5])
    ws2 = wb.create_sheet("Names")
    ws2.append(["who", "where"])
    ws2.append(["alice", "boston"])
    wb.save(p)
    return p


def test_is_supported_extensions():
    assert is_supported("a.xlsx")
    assert is_supported("a.xlsm")
    assert is_supported("a.ods")
    assert is_supported("a.xls")
    assert not is_supported("a.csv")
    assert not is_supported("a.txt")


def test_extension_sets():
    assert ".xlsx" in XLSX_EXTENSIONS
    assert ".ods" in ODS_EXTENSIONS
    assert ".xls" in LEGACY_XLS_EXTENSIONS
    assert not (XLSX_EXTENSIONS & ODS_EXTENSIONS)


def test_xlsx_list_sheets(two_sheet_xlsx):
    assert list_sheets(str(two_sheet_xlsx)) == ["Numbers", "Names"]


def test_xlsx_first_sheet_to_csv(two_sheet_xlsx):
    csv_text = load_sheet_as_csv(str(two_sheet_xlsx), 0)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "a,b,c"
    # Integers stay int-shaped, floats keep their decimals.
    assert lines[1] == "1,2,3.5"
    assert lines[2] == "4,5,6.5"


def test_xlsx_by_sheet_name(two_sheet_xlsx):
    csv_text = load_sheet_as_csv(str(two_sheet_xlsx), "Names")
    lines = csv_text.strip().splitlines()
    assert lines[0] == "who,where"
    assert lines[1] == "alice,boston"


def test_xlsx_out_of_range_sheet(two_sheet_xlsx):
    with pytest.raises(SpreadsheetReadError):
        load_sheet_as_csv(str(two_sheet_xlsx), 99)


def test_xlsx_unknown_sheet_name(two_sheet_xlsx):
    with pytest.raises(SpreadsheetReadError):
        load_sheet_as_csv(str(two_sheet_xlsx), "Nope")


def test_unsupported_extension_raises():
    with pytest.raises(SpreadsheetReadError):
        list_sheets("not_a_workbook.csv")


def test_file_loader_routes_xlsx_through(tmp_path):
    """The high-level `file_loader.load_file` should detect xlsx, route
    through the spreadsheet loader, and return CSV-shaped content."""
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "x.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "S1"
    ws.append(["k", "v"]); ws.append([10, 20])
    wb.save(p)

    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "xlsx"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "xlsx"
    assert "k,v" in content and "10,20" in content
    assert "sheet=" in encoding  # "xlsx · sheet=S1"


def test_int_floats_dont_get_decimal(tmp_path):
    """Cells like `5` in openpyxl come back as 5.0; we want them as
    '5' in the CSV, not '5.0'."""
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "ints.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["x"])
    ws["A2"] = 5.0  # openpyxl writes this as a float
    wb.save(p)
    out = load_sheet_as_csv(str(p), 0)
    assert "5" in out.splitlines()[1] and "5.0" not in out


def test_empty_workbook_returns_empty_csv(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "empty.xlsx"
    wb = openpyxl.Workbook(); wb.save(p)
    assert load_sheet_as_csv(str(p), 0).strip() == ""


@pytest.mark.skipif(not _have(["pandas", "odf"]), reason="pandas+odfpy not installed")
def test_ods_round_trip(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("odf")
    p = tmp_path / "doc.ods"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(p, engine="odf", index=False)
    sheets = list_sheets(str(p))
    assert len(sheets) >= 1
    csv_text = load_sheet_as_csv(str(p), 0)
    assert "1" in csv_text and "4" in csv_text

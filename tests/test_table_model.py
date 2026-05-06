"""TableModel: parsing, edit, sort, filter, derived column, serialize.

Includes regression for the CSV edit-cycle bug where edits made via
setData were not reflected back when serialize() was called for a code-
view round-trip.
"""
from PyQt6.QtCore import Qt
from src.table_model import TableModel, parse_delimited, to_number


def test_parse_delimited_autodetects_comma(sample_csv):
    header, rows, delim = parse_delimited(sample_csv)
    assert delim == ","
    assert header == ["name", "age", "city", "score"]
    assert len(rows) == 3
    assert rows[0] == ["Alice", "30", "Boston", "92.5"]


def test_parse_delimited_supports_tab():
    text = "a\tb\nc\td\n"
    header, rows, delim = parse_delimited(text)
    assert delim == "\t"
    assert rows == [["c", "d"]]


def test_to_number_handles_floats_and_ints():
    assert to_number("42") == 42.0
    assert to_number("-3.14") == -3.14
    assert to_number("1e3") == 1000.0
    assert to_number("not a number") is None
    assert to_number("") is None


def test_set_data_updates_underlying_row(qapp, sample_csv):
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows); m._editable = True
    assert m.setData(m.index(0, 0), "ZARA", Qt.ItemDataRole.EditRole)
    assert m.get_value(0, 0) == "ZARA"
    assert m._rows[0][0] == "ZARA"


def test_serialize_reflects_setdata_edits(qapp, sample_csv):
    """Regression: the CSV-edit-reflection bug found that setData edits
    were not present in the serialize() output when the code view was
    re-populated. They must be."""
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows); m._editable = True
    m.setData(m.index(0, 0), "ZARA", Qt.ItemDataRole.EditRole)
    m.setData(m.index(0, 3), "1234.5", Qt.ItemDataRole.EditRole)
    out = m.serialize(",")
    assert "ZARA" in out
    assert "1234.5" in out
    assert "Alice" not in out  # original value gone


def test_sort_numeric_ascending_then_descending(qapp, sample_csv):
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows)
    m.sort(3, Qt.SortOrder.AscendingOrder)
    visible = [m.get_value(r, 0) for r in range(m.rowCount())]
    assert visible == ["Bob", "Alice", "Carol"]  # 85.0 < 92.5 < 98.2
    m.sort(3, Qt.SortOrder.DescendingOrder)
    visible = [m.get_value(r, 0) for r in range(m.rowCount())]
    assert visible == ["Carol", "Alice", "Bob"]


def test_filter_restricts_visible_rows(qapp, sample_csv):
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows)
    m.set_filter(3, ">", "90")
    assert m.rowCount() == 2  # Alice 92.5, Carol 98.2
    m.clear_filter()
    assert m.rowCount() == 3


def test_add_derived_column_evaluates_per_row(qapp, sample_csv):
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows)
    m.add_derived_column("score_per_age", "score / age")
    assert "score_per_age" in m.header()
    col = m.header().index("score_per_age")
    val0 = float(m.get_value(0, col))  # Alice: 92.5 / 30
    # Stored as `{val:g}` (6 sig figs), so loose tolerance.
    assert abs(val0 - 92.5 / 30) < 1e-4


def test_add_derived_column_rejects_dunder_access(qapp, sample_csv):
    """The derived-column formula evaluator must not let users escape
    into __builtins__. Every row's eval should fail, the column should
    NOT be added, and the model state should be untouched."""
    h, rows, _ = parse_delimited(sample_csv)
    m = TableModel(h, rows)
    cols_before = list(m.header())
    ok, msg = m.add_derived_column("evil", "__import__('os').system('echo HACKED')")
    assert ok is False
    assert m.header() == cols_before  # column not added
    # Underlying row data is untouched.
    assert m.get_value(0, 0) == "Alice"

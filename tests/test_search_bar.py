"""SearchBar: regex find/replace with backref expansion + bad-pattern handling."""
from PyQt6.QtWidgets import QPlainTextEdit
from src.search_bar import SearchBar


def _bar(qapp, text):
    edit = QPlainTextEdit(text); edit.setReadOnly(False)
    sb = SearchBar(); sb.attach(edit); sb.set_replace_enabled(True)
    return sb, edit


def test_regex_find_next_matches_first_pattern(qapp):
    sb, edit = _bar(qapp, "foo 42 bar 100 baz")
    sb.cb_regex.setChecked(True); sb.find_input.setText(r"\d+")
    sb.find_next()
    assert edit.textCursor().selectedText() == "42"


def test_regex_replace_all_with_backref(qapp):
    sb, edit = _bar(qapp, "Hello Alice. Hello Bob.")
    sb.cb_regex.setChecked(True)
    sb.find_input.setText(r"Hello (\w+)")
    sb.replace_input.setText(r"Hi \1")
    sb.replace_all()
    assert edit.toPlainText() == "Hi Alice. Hi Bob."


def test_literal_replace_all_unchanged_when_regex_off(qapp):
    sb, edit = _bar(qapp, "abc abc abc")
    sb.find_input.setText("abc"); sb.replace_input.setText("XYZ")
    sb.replace_all()
    assert edit.toPlainText() == "XYZ XYZ XYZ"


def test_regex_replace_one_advances(qapp):
    sb, edit = _bar(qapp, "a1 b2 c3")
    sb.cb_regex.setChecked(True)
    sb.find_input.setText(r"([a-z])(\d)")
    sb.replace_input.setText(r"\2\1")
    sb.find_next()
    sb.replace_one()
    assert edit.toPlainText() == "1a b2 c3"


def test_bad_regex_does_not_mutate_buffer(qapp):
    sb, edit = _bar(qapp, "foo bar")
    sb.cb_regex.setChecked(True)
    sb.find_input.setText(r"foo[")
    sb.replace_input.setText("baz")
    sb.replace_all()
    assert edit.toPlainText() == "foo bar"
    assert "Bad" in sb.status.text()


def test_case_insensitive_regex_replace(qapp):
    sb, edit = _bar(qapp, "Hello HELLO hello")
    sb.cb_regex.setChecked(True)
    sb.cb_case.setChecked(False)
    sb.find_input.setText(r"hello"); sb.replace_input.setText("hi")
    sb.replace_all()
    assert edit.toPlainText() == "hi hi hi"

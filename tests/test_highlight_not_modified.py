"""Regression: re-styling (view_styler.apply_line_height, renderers.apply_pygments) set the
document's modified flag, so merely opening a code file made TextView ask
"There are unsaved changes" on the next open / tab switch / close."""
import os
from pathlib import Path


def test_opening_code_file_is_not_modified(qapp):
    os.chdir(Path(__file__).resolve().parent.parent)
    from PyQt6 import QtWebEngineWidgets  # noqa: F401
    from src.app import MainWindow
    w = MainWindow(); w.show(); qapp.processEvents()
    w.open_file("sample_files/example.py", confirm=False); qapp.processEvents()
    assert w._current_format == "python"
    assert not w.viewer.code.document().isModified()
    assert w.edit.modified is False
    w.close()


def test_apply_pygments_keeps_existing_modified_flag(qapp):
    from PyQt6.QtWidgets import QPlainTextEdit
    from src.renderers import apply_pygments
    ed = QPlainTextEdit(); ed.setPlainText("x = 1\n")
    ed.document().setModified(True)
    apply_pygments(ed, "x = 1\n", format_hint="python")
    assert ed.document().isModified()


def test_apply_line_height_keeps_modified_flag(qapp):
    from PyQt6.QtWidgets import QPlainTextEdit
    from src.view_styler import apply_line_height
    ed = QPlainTextEdit(); ed.setPlainText("a\nb\n")
    ed.document().setModified(False)
    apply_line_height(ed, 1.6)
    assert not ed.document().isModified()

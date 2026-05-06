"""Citation panel: populate from chunks + click → emit open_requested."""
from src.citation_panel import CitationPanel, open_at_locator
from src.workspace_index import Chunk


def _make_chunks():
    return [
        Chunk(path="/tmp/a.py", kind="code", locator="line:5", text="def foo(): pass", title="a.py:5"),
        Chunk(path="/tmp/notes.md", kind="text", locator="line:1", text="# notes", title="notes.md:1"),
        Chunk(path="/tmp/x.pdf", kind="pdf", locator="page:3", text="page body", title="x.pdf p3"),
        Chunk(path="/tmp/n.ipynb", kind="notebook", locator="cell:0", text="import sys", title="n.ipynb cell 1"),
    ]


def test_set_citations_populates_rows(qapp):
    p = CitationPanel()
    p.set_citations(_make_chunks(), query="foo")
    assert p.row_count() == 4
    assert "4 match(es) for 'foo'" in p.lbl_query.text()


def test_set_citations_with_no_query(qapp):
    p = CitationPanel()
    p.set_citations(_make_chunks())
    assert p.row_count() == 4
    assert "4 citation" in p.lbl_query.text()


def test_clear_resets_state(qapp):
    p = CitationPanel()
    p.set_citations(_make_chunks(), query="foo")
    p.clear()
    assert p.row_count() == 0
    assert "no query yet" in p.lbl_query.text()


def test_activating_row_emits_open_requested(qapp):
    p = CitationPanel()
    p.set_citations(_make_chunks(), query="foo")
    captured = []
    p.open_requested.connect(lambda path, loc: captured.append((path, loc)))
    p._on_activated(p.list.item(0))
    assert captured == [("/tmp/a.py", "line:5")]


def test_window_title_shows_count(qapp):
    p = CitationPanel()
    p.set_citations(_make_chunks(), query="x")
    assert "(4)" in p.windowTitle()


# -- open_at_locator router -------------------------------------------------

class _FakeViewer:
    def __init__(self):
        from PyQt6.QtWidgets import QPlainTextEdit
        self.code = QPlainTextEdit()


class _FakeWindow:
    def __init__(self):
        self.viewer = _FakeViewer()
        self.opened = []
    def open_file(self, path): self.opened.append(path)


def test_open_at_locator_with_line_jumps_cursor(qapp):
    from PyQt6.QtGui import QTextCursor
    w = _FakeWindow()
    w.viewer.code.setPlainText("\n".join(f"line {i}" for i in range(20)))
    open_at_locator(w, "/tmp/x.py", "line:7")
    assert w.opened == ["/tmp/x.py"]
    # Cursor should be on line 7 (block number 6, 0-indexed).
    assert w.viewer.code.textCursor().blockNumber() == 6


def test_open_at_locator_no_path_no_op(qapp):
    w = _FakeWindow()
    assert open_at_locator(w, "", "line:1") is False
    assert w.opened == []


def test_open_at_locator_blank_locator_just_opens(qapp):
    w = _FakeWindow()
    assert open_at_locator(w, "/tmp/y.png", "") is True
    assert w.opened == ["/tmp/y.png"]


def test_open_at_locator_garbage_locator_just_opens(qapp):
    w = _FakeWindow()
    assert open_at_locator(w, "/tmp/y.py", "weird:not-a-number") is True
    assert w.opened == ["/tmp/y.py"]

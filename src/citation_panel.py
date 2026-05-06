"""Citation panel — the click-through bridge from agent answers to files.

When a `query_workspace(...)` tool runs, it pushes its results into this
panel. Each row is a `(path, locator, snippet)` citation; activating a
row opens the file at the right line / page / cell via `open_at_locator`.

This is the "agent shows you the files" loop made concrete.
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDockWidget, QListWidget, QListWidgetItem, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton,
)


_KIND_COLOR = {
    "code":     "#3b8eea",
    "text":     "#7aa884",
    "pdf":      "#e74c3c",
    "notebook": "#fb8c00",
    "image":    "#9c27b0",
}


class CitationPanel(QDockWidget):
    """Right-side dock listing the most recent RAG citations."""

    open_requested = pyqtSignal(str, str)   # path, locator

    def __init__(self, parent=None):
        super().__init__("Citations", parent)
        self.setObjectName("citation_panel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea)
        body = QWidget(); v = QVBoxLayout(body); v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        bar = QHBoxLayout(); bar.setContentsMargins(2, 2, 2, 2)
        self.lbl_query = QLabel("(no query yet)")
        self.lbl_query.setStyleSheet("color: #888;")
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedWidth(60)
        bar.addWidget(self.lbl_query, 1); bar.addWidget(self.btn_clear)
        v.addLayout(bar)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        v.addWidget(self.list, 1)
        self.setWidget(body)

        self.list.itemActivated.connect(self._on_activated)
        self.btn_clear.clicked.connect(self.clear)
        self._citations: list = []     # list[Chunk]
        self._query: str = ""

    def set_citations(self, chunks: list, query: str = ""):
        """Replace the panel contents with the given citations."""
        self._citations = list(chunks or [])
        self._query = query or ""
        self.list.clear()
        n = len(self._citations)
        if query: self.lbl_query.setText(f"{n} match(es) for {query!r}")
        else:     self.lbl_query.setText(f"{n} citation(s)")
        cwd = Path.cwd()
        for i, ch in enumerate(self._citations):
            try: rel = str(Path(ch.path).relative_to(cwd))
            except (ValueError, AttributeError): rel = getattr(ch, "path", str(ch))
            loc = getattr(ch, "locator", "") or "(file)"
            kind = getattr(ch, "kind", "")
            snippet = " ".join((ch.text or "").split())[:140]
            label = f"{rel}  ·  {loc}\n    {snippet}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ch)
            color = _KIND_COLOR.get(kind)
            if color: item.setForeground(QColor(color))
            self.list.addItem(item)
        self.setWindowTitle(f"Citations ({n})")
        if self._citations: self.show()

    def clear(self):
        self._citations = []
        self._query = ""
        self.list.clear()
        self.lbl_query.setText("(no query yet)")
        self.setWindowTitle("Citations")

    def citations(self) -> list:
        return list(self._citations)

    def row_count(self) -> int:
        return self.list.count()

    def _on_activated(self, item: QListWidgetItem):
        ch = item.data(Qt.ItemDataRole.UserRole)
        if ch is None: return
        path = getattr(ch, "path", None)
        loc  = getattr(ch, "locator", "") or ""
        if path: self.open_requested.emit(path, loc)


# ---- open-at-locator router -----------------------------------------------

def open_at_locator(window, path: str, locator: str = "") -> bool:
    """Open `path` in `window` and jump to `locator` (line:N / page:N /
    cell:N / empty). Returns True on a navigated open."""
    if not path: return False
    window.open_file(path)
    if not locator: return True
    try: kind, val = locator.split(":", 1)
    except ValueError: return True
    try: n = int(val)
    except ValueError: return True
    if kind == "line":
        _jump_to_line(window, n)
    elif kind == "page":
        _jump_to_pdf_page(window, n)
    elif kind == "cell":
        _jump_to_notebook_cell(window, n)
    return True


def _jump_to_line(window, line_1_based: int):
    from PyQt6.QtGui import QTextCursor
    cv = window.viewer.code
    c = cv.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    c.movePosition(QTextCursor.MoveOperation.Down, n=max(0, line_1_based - 1))
    cv.setTextCursor(c); cv.centerCursor()


def _jump_to_pdf_page(window, page_1_based: int):
    """Navigate the PDF view to a page. Best-effort across PyQt6 versions."""
    pdf_view = getattr(window.viewer, "pdf_view", None)
    if pdf_view is None: return
    try:
        nav = pdf_view.pageNavigator()
        nav.jump(max(0, page_1_based - 1), pdf_view.pageNavigator().currentLocation()
                 if hasattr(pdf_view.pageNavigator(), "currentLocation") else None,
                 pdf_view.pageNavigator().currentZoom()
                 if hasattr(pdf_view.pageNavigator(), "currentZoom") else 1.0)
    except Exception:
        # Fallback: jump via setCurrentPage if available.
        try: pdf_view.setCurrentPage(max(0, page_1_based - 1))
        except Exception: pass


def _jump_to_notebook_cell(window, cell_idx: int):
    nv = getattr(window.viewer, "notebook_view", None)
    if nv is None: return
    cells = nv.cells() if hasattr(nv, "cells") else []
    if 0 <= cell_idx < len(cells):
        c = cells[cell_idx]
        try: c.body.setFocus(); nv.ensureWidgetVisible(c)
        except Exception: pass

"""Indent-based code folding for `CodeViewer`.

A foldable block is one whose next non-blank block is at strictly greater
indentation. Folding hides every following block that is more indented
than the fold's anchor, until indentation returns to the anchor's level
(or end-of-document). Works for Python's `:`-blocks and for C-family
braced bodies because braced bodies are conventionally indented too.
"""
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QPainter, QPolygon
from PyQt6.QtCore import QPoint


def _indent_of(text: str) -> int:
    return len(text) - len(text.lstrip())


def _next_nonblank(block):
    nxt = block.next()
    while nxt.isValid() and not nxt.text().strip():
        nxt = nxt.next()
    return nxt


class FoldController:
    """Owns per-block fold state for an attached `QPlainTextEdit`."""

    MARKER_W = 14  # gutter column in px

    def __init__(self, editor):
        self.editor = editor
        self.enabled = False
        self.color = QColor("#888888")
        self._folded: set[int] = set()  # block numbers explicitly folded

    def set_enabled(self, on: bool):
        if on == self.enabled: return
        self.enabled = on
        if not on: self.unfold_all()
        self.editor._update_line_number_area_width()
        self.editor._line_number_area.update()

    def is_foldable(self, block) -> bool:
        if not self.enabled or not block.isValid(): return False
        if not block.text().strip(): return False
        nxt = _next_nonblank(block)
        return nxt.isValid() and _indent_of(nxt.text()) > _indent_of(block.text())

    def is_folded(self, block) -> bool:
        return block.blockNumber() in self._folded

    def toggle(self, block):
        if not self.is_foldable(block): return
        if self.is_folded(block): self._unfold(block)
        else:                     self._fold(block)
        doc = self.editor.document()
        doc.markContentsDirty(block.position(), doc.characterCount() - block.position())
        self.editor.viewport().update()
        self.editor._line_number_area.update()

    def _children(self, block):
        anchor = _indent_of(block.text())
        nxt = block.next()
        while nxt.isValid():
            txt = nxt.text()
            if txt.strip() and _indent_of(txt) <= anchor: break
            yield nxt
            nxt = nxt.next()

    def _fold(self, block):
        self._folded.add(block.blockNumber())
        for b in self._children(block): b.setVisible(False)

    def _unfold(self, block):
        # Discard explicit fold; reveal descendants except those whose own
        # ancestor (within this subtree) is still in `_folded`.
        self._folded.discard(block.blockNumber())
        anchor = _indent_of(block.text())
        # Stack of (block_number, indent) for folded ancestors crossed.
        stack: list[tuple[int, int]] = []
        nxt = block.next()
        while nxt.isValid():
            txt = nxt.text()
            ind = _indent_of(txt) if txt.strip() else None
            if ind is not None and ind <= anchor: break
            while stack and ind is not None and ind <= stack[-1][1]:
                stack.pop()
            if not stack:
                nxt.setVisible(True)
                if nxt.blockNumber() in self._folded:
                    stack.append((nxt.blockNumber(), ind or 0))
            nxt = nxt.next()

    def unfold_all(self):
        self._folded.clear()
        block = self.editor.document().firstBlock()
        while block.isValid():
            block.setVisible(True); block = block.next()
        self.editor.document().markContentsDirty(0, self.editor.document().characterCount())
        self.editor.viewport().update()
        self.editor._line_number_area.update()

    def paint_marker(self, painter: QPainter, x: int, y: int, h: int, folded: bool):
        """Draw a tiny triangle: ▶ when folded, ▼ when open."""
        painter.save()
        painter.setPen(self.color); painter.setBrush(self.color)
        cy = y + h // 2; size = 4
        if folded:  # right-pointing
            pts = QPolygon([QPoint(x, cy - size), QPoint(x, cy + size), QPoint(x + size, cy)])
        else:        # down-pointing
            pts = QPolygon([QPoint(x - size, cy - 1), QPoint(x + size, cy - 1), QPoint(x, cy + size - 1)])
        painter.drawPolygon(pts)
        painter.restore()

    def block_at(self, y: int):
        """Return the block whose paint rect contains screen-y `y`, or None."""
        block = self.editor.firstVisibleBlock()
        top = round(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        while block.isValid():
            h = round(self.editor.blockBoundingRect(block).height())
            if block.isVisible() and top <= y < top + h:
                return block
            if block.isVisible(): top += h
            block = block.next()
        return None

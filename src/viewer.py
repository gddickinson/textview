"""The viewer widgets: a code-style read-only editor with a line-number
gutter and current-line highlight, plus a stacked widget that flips between
that and a `QTextBrowser` for rendered HTML/markdown.
"""
import re

from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QStackedWidget, QTextBrowser, QTextEdit,
)
from PyQt6.QtCore import Qt, QRect, QSize, QUrl, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QTextFormat, QTextOption, QDesktopServices, QTextCursor,
)
from .image_view import ImageView
from .web_view import WebView
from .pdf_viewer import PdfViewer
from .video_view import VideoView
from .table_view import TableView
from .code_fold import FoldController


# Conservative URL matcher used for Ctrl+click in plain text.
_URL_RE = re.compile(r'(?:https?|ftp|file)://[^\s<>"\'`(){}\[\]]+')

# Bracket pairs auto-closed when the editor is editable.
_AUTO_CLOSE = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`"}
_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {v: k for k, v in _OPEN_TO_CLOSE.items()}


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint(event)

    def mousePressEvent(self, event):
        # Forward clicks in the fold-marker column to the FoldController.
        f = self.editor.fold
        if f.enabled and event.position().x() >= self.width() - f.MARKER_W:
            blk = f.block_at(int(event.position().y()))
            if blk is not None and f.is_foldable(blk):
                f.toggle(blk); event.accept(); return
        super().mousePressEvent(event)


class CodeViewer(QPlainTextEdit):
    """Code/text view with line numbers, current-line highlight, optional
    whitespace rendering, and Ctrl+click URL following.
    """

    # Emitted when the mouse has been still over this viewer for ~600ms.
    # Carries the viewport-relative point. Used by the LSP layer to fire
    # `textDocument/hover` requests.
    cursor_paused = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(self.Shape.NoFrame)
        self.setMouseTracking(True)
        self._hover_timer = QTimer(self); self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(600)
        self._hover_timer.timeout.connect(self._emit_cursor_paused)
        self._last_mouse_pos = QPoint(-1, -1)
        self._hover_enabled = False  # gated by MainWindow per settings flag

        self._line_number_area = LineNumberArea(self)
        self.fold = FoldController(self)
        self._diagnostics: list[dict] = []  # raw LSP diagnostic dicts
        self._show_line_numbers = True
        self._line_number_bg = QColor("#252526")
        self._line_number_fg = QColor("#808080")
        self._current_line_color = QColor("#2a2d2e")
        self._bracket_match_color = QColor("#3c3f41")
        self._highlight_current = True

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width()
        self._highlight_current_line()

    # -- public configuration ------------------------------------------------

    def set_diagnostics(self, diagnostics: list):
        """Replace the per-block diagnostic markers and repaint the gutter."""
        self._diagnostics = list(diagnostics) if diagnostics else []
        self._line_number_area.update()

    def diagnostics_at_line(self, line: int) -> list:
        return [d for d in self._diagnostics
                if (d.get("range") or {}).get("start", {}).get("line") == line]

    def set_show_line_numbers(self, show: bool):
        self._show_line_numbers = show
        self._line_number_area.setVisible(show)
        self._update_line_number_area_width()

    def set_line_number_colors(self, bg: str, fg: str):
        self._line_number_bg = QColor(bg)
        self._line_number_fg = QColor(fg)
        self._line_number_area.update()

    def set_current_line_color(self, color: str):
        self._current_line_color = QColor(color)
        self._highlight_current_line()

    def set_bracket_match_color(self, color: str):
        self._bracket_match_color = QColor(color)
        self._highlight_current_line()

    def set_highlight_current(self, on: bool):
        self._highlight_current = on
        self._highlight_current_line()

    def set_show_whitespace(self, on: bool):
        opt = self.document().defaultTextOption()
        flags = opt.flags()
        ws_flag = QTextOption.Flag.ShowTabsAndSpaces
        sep_flag = QTextOption.Flag.ShowLineAndParagraphSeparators
        if on:
            flags |= ws_flag | sep_flag
        else:
            flags &= ~ws_flag
            flags &= ~sep_flag
        opt.setFlags(flags)
        self.document().setDefaultTextOption(opt)
        self.viewport().update()

    # -- gutter rendering ----------------------------------------------------

    def line_number_area_width(self) -> int:
        if not self._show_line_numbers:
            return self.fold.MARKER_W if self.fold.enabled else 0
        digits = max(3, len(str(max(1, self.blockCount()))))
        base = 16 + self.fontMetrics().horizontalAdvance("9") * digits
        return base + (self.fold.MARKER_W if self.fold.enabled else 0)

    def _update_line_number_area_width(self, *_):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint(self, event):
        if not self._show_line_numbers and not self.fold.enabled:
            return
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), self._line_number_bg)
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        painter.setPen(self._line_number_fg)
        right_pad = 8 + (self.fold.MARKER_W if self.fold.enabled else 0)
        width = self._line_number_area.width() - right_pad
        line_height = self.fontMetrics().height()
        marker_x = self._line_number_area.width() - self.fold.MARKER_W + 4
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if self._show_line_numbers:
                    painter.drawText(
                        0, top, width, line_height,
                        Qt.AlignmentFlag.AlignRight, str(block_number + 1),
                    )
                if self.fold.enabled and self.fold.is_foldable(block):
                    self.fold.paint_marker(painter, marker_x, top, line_height,
                                           self.fold.is_folded(block))
                if self._diagnostics:
                    self._paint_diagnostic_dot(painter, block_number, top, line_height)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    _DIAG_COLORS = {1: "#e53935", 2: "#fb8c00", 3: "#039be5", 4: "#9e9e9e"}

    def _paint_diagnostic_dot(self, painter, block_number: int, top: int, h: int):
        diags = self.diagnostics_at_line(block_number)
        if not diags: return
        sev = min(d.get("severity", 1) for d in diags)
        color = QColor(self._DIAG_COLORS.get(sev, "#e53935"))
        painter.save()
        painter.setBrush(color); painter.setPen(color)
        cy = top + h // 2
        painter.drawEllipse(2, cy - 3, 6, 6)
        painter.restore()

    def _highlight_current_line(self):
        selections = []
        if self._highlight_current:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(self._current_line_color)
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        # Matching-bracket highlight: when the cursor is right next to a
        # bracket character, scan in the direction of the pair and add a
        # subtle box around both members so the user can see balance at a
        # glance.
        for sel in self._matching_bracket_selections():
            selections.append(sel)
        self.setExtraSelections(selections)

    def _matching_bracket_selections(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return []
        doc = self.document()
        pos = cursor.position()
        # Look at the char to the right; fall through to the left.
        for probe in (pos, pos - 1):
            if probe < 0:
                continue
            ch = doc.characterAt(probe)
            if ch in _OPEN_TO_CLOSE:
                target = self._find_matching_bracket(probe, ch, +1)
            elif ch in _CLOSE_TO_OPEN:
                target = self._find_matching_bracket(probe, ch, -1)
            else:
                continue
            if target is None:
                continue
            return self._bracket_selections(doc, probe, target)
        return []

    def _bracket_selections(self, doc, a: int, b: int):
        from PyQt6.QtGui import QTextCharFormat
        fmt = QTextCharFormat(); fmt.setBackground(self._bracket_match_color)
        out = []
        for p in (a, b):
            sel = QTextEdit.ExtraSelection(); sel.format = fmt
            c = QTextCursor(doc); c.setPosition(p)
            c.setPosition(p + 1, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            out.append(sel)
        return out

    def _find_matching_bracket(self, start_pos: int, ch: str, direction: int):
        """Walk the document forward (+1) or backward (-1) counting brackets."""
        opens = set(_OPEN_TO_CLOSE) if direction > 0 else set(_CLOSE_TO_OPEN)
        closes = set(_OPEN_TO_CLOSE.values()) if direction > 0 else set(_OPEN_TO_CLOSE)
        target = (_OPEN_TO_CLOSE if direction > 0 else _CLOSE_TO_OPEN)[ch]
        doc = self.document()
        depth = 0
        pos = start_pos + direction
        end = doc.characterCount()
        max_scan = 50_000   # don't scan multi-megabyte files
        while 0 <= pos < end and max_scan > 0:
            c = doc.characterAt(pos)
            if c == ch:
                depth += 1
            elif c == target:
                if depth == 0:
                    return pos
                depth -= 1
            pos += direction
            max_scan -= 1
        return None

    # -- key handling: auto-close brackets, auto-indent on Enter ------------

    def keyPressEvent(self, event):
        if self.isReadOnly():
            super().keyPressEvent(event)
            return
        text = event.text()
        cursor = self.textCursor()
        # Skip-over an already-present closing char: typing `)` when next
        # char is `)` just moves the cursor past it.
        if text in (")", "]", "}", '"', "'", "`"):
            doc = self.document()
            if doc.characterAt(cursor.position()) == text and not cursor.hasSelection():
                cursor.movePosition(QTextCursor.MoveOperation.Right)
                self.setTextCursor(cursor)
                event.accept()
                return
        # Auto-close: insert pair, place cursor between them.
        if text in _AUTO_CLOSE and not cursor.hasSelection():
            doc = self.document()
            nxt = doc.characterAt(cursor.position())
            if not nxt or nxt.isspace() or nxt in ")]}':\"`>,;":
                close = _AUTO_CLOSE[text]
                cursor.beginEditBlock()
                cursor.insertText(text + close)
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                event.accept()
                return
        # Auto-indent on Enter: copy leading whitespace; add one extra
        # indent step if the line ends with `:` (Python) or `{` (C-like).
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            block = cursor.block()
            line = block.text()
            indent = line[:len(line) - len(line.lstrip())]
            stripped = line.rstrip()
            extra = "    " if stripped.endswith((":", "{", "(", "[")) else ""
            cursor.insertText("\n" + indent + extra)
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)

    # -- line operations ----------------------------------------------------

    def move_line(self, direction: int):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                QTextCursor.MoveMode.KeepAnchor)
            line = cursor.selectedText()
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the trailing newline
            cursor.movePosition(
                QTextCursor.MoveOperation.Up if direction < 0 else QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.MoveAnchor,
            )
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertText(line + "\n")
            cursor.movePosition(QTextCursor.MoveOperation.Up)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)

    def duplicate_line(self):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        block = cursor.block()
        line = block.text()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText("\n" + line)
        cursor.endEditBlock()

    def select_line(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    # -- Ctrl+click URL following --------------------------------------------

    def _url_at(self, point):
        cursor = self.cursorForPosition(point)
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()
        for m in _URL_RE.finditer(text):
            if m.start() <= col <= m.end():
                return m.group(0)
        return None

    def mouseMoveEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            url = self._url_at(event.position().toPoint())
            self.viewport().setCursor(
                Qt.CursorShape.PointingHandCursor if url else Qt.CursorShape.IBeamCursor
            )
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        if self._hover_enabled:
            self._last_mouse_pos = event.position().toPoint()
            self._hover_timer.start()  # restart debounce
        super().mouseMoveEvent(event)

    def set_hover_pause_enabled(self, on: bool):
        self._hover_enabled = bool(on)
        if not on: self._hover_timer.stop()

    def _emit_cursor_paused(self):
        if self._last_mouse_pos.x() >= 0:
            self.cursor_paused.emit(self._last_mouse_pos)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            url = self._url_at(event.position().toPoint())
            if url:
                QDesktopServices.openUrl(QUrl(url))
                event.accept()
                return
        super().mouseReleaseEvent(event)


class TextViewer(QStackedWidget):
    """Switches between the code-style viewer, rendered HTML, and a PDF view."""

    MODE_CODE = "code"
    MODE_RENDERED = "rendered"
    MODE_PDF = "pdf"
    MODE_IMAGE = "image"
    MODE_WEB = "web"
    MODE_VIDEO = "video"
    MODE_TABLE = "table"
    MODE_NOTEBOOK = "notebook"
    MODE_ARCHIVE = "archive"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.code = CodeViewer()
        self.rendered = QTextBrowser()
        self.rendered.setOpenExternalLinks(True)
        self.rendered.setFrameShape(self.code.Shape.NoFrame)
        self.pdf_view = PdfViewer(self)
        self.image_view = ImageView(self)
        self.web_view = WebView(self)
        self.video_view = VideoView(self)
        self.table_view = TableView(self)
        from .notebook_view import NotebookView
        self.notebook_view = NotebookView(self)
        from .archive_view import ArchiveView
        self.archive_view = ArchiveView(self)
        for w in (self.code, self.rendered, self.pdf_view, self.image_view,
                  self.web_view, self.video_view, self.table_view,
                  self.notebook_view, self.archive_view):
            self.addWidget(w)
        self._mode = self.MODE_CODE

    def show_code(self):
        self.setCurrentWidget(self.code)
        self._mode = self.MODE_CODE

    def show_rendered(self):
        self.setCurrentWidget(self.rendered)
        self._mode = self.MODE_RENDERED

    def show_pdf(self):
        self.setCurrentWidget(self.pdf_view)
        self._mode = self.MODE_PDF

    def show_image(self):
        self.setCurrentWidget(self.image_view)
        self._mode = self.MODE_IMAGE

    def show_web(self):
        self.setCurrentWidget(self.web_view)
        self._mode = self.MODE_WEB

    def show_video(self):
        self.setCurrentWidget(self.video_view)
        self._mode = self.MODE_VIDEO

    def show_table(self):
        self.setCurrentWidget(self.table_view)
        self._mode = self.MODE_TABLE

    def mode(self) -> str:
        return self._mode

    def show_notebook(self):
        self.setCurrentWidget(self.notebook_view); self._mode = self.MODE_NOTEBOOK

    def show_archive(self):
        self.setCurrentWidget(self.archive_view); self._mode = self.MODE_ARCHIVE

    def active_widget(self):
        m = {
            self.MODE_CODE: self.code, self.MODE_RENDERED: self.rendered,
            self.MODE_PDF: self.pdf_view, self.MODE_IMAGE: self.image_view,
            self.MODE_VIDEO: self.video_view, self.MODE_TABLE: self.table_view,
            self.MODE_NOTEBOOK: self.notebook_view, self.MODE_WEB: self.web_view,
            self.MODE_ARCHIVE: self.archive_view,
        }
        return m.get(self._mode, self.web_view)

"""Interactive shell terminal — pyte-emulated VT100 in a Qt widget.

`TerminalWidget` is a `QPlainTextEdit` subclass that:
  - Spawns a shell via `PtyProcess` (default `$SHELL` or /bin/bash).
  - Feeds incoming bytes to a `pyte.Screen` so cursor moves, line
    clears, attributes and color codes are interpreted properly. This
    is what makes `vim`, `top`, `clear`, etc. work — bare ANSI rendering
    only handles colors.
  - Re-renders only the rows pyte marked dirty after each chunk.
  - Captures keystrokes and encodes them to PTY bytes (escape sequences
    for arrows, function keys, Home/End, plus Ctrl+letter → control
    byte).
  - On resize, recomputes (rows, cols) from font metrics and pushes
    both to pyte and the kernel via TIOCSWINSZ.

`TerminalDock` wraps it in a `QDockWidget` with a small toolbar
(Restart, Kill, status label).
"""
import os

import pyte
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QFont, QFontMetrics, QTextCharFormat, QColor, QTextCursor, QPalette,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QPlainTextEdit, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QLabel,
)

from .pty_process import PtyProcess


_NAMED_COLORS = {
    "black":   "#000000",
    "red":     "#cd3131",
    "green":   "#0dbc79",
    "yellow":  "#e5e510",
    "blue":    "#2472c8",
    "magenta": "#bc3fbc",
    "cyan":    "#11a8cd",
    "white":   "#cccccc",
    "brown":   "#e5e510",   # pyte's "brown" → bright yellow
}

_BRIGHT_NAMED = {
    "black":   "#666666",
    "red":     "#f14c4c",
    "green":   "#23d18b",
    "yellow":  "#f5f543",
    "blue":    "#3b8eea",
    "magenta": "#d670d6",
    "cyan":    "#29b8db",
    "white":   "#e5e5e5",
}

_FG_DEFAULT = "#cccccc"
_BG_DEFAULT = "#1e1e1e"


def _color(c: str, default: str, bright: bool = False) -> str:
    if not c or c == "default":
        return default
    # pyte 24-bit colors come through as 6 hex digits without '#'
    if isinstance(c, str) and len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return "#" + c.lower()
    table = _BRIGHT_NAMED if bright else _NAMED_COLORS
    return table.get(c, _NAMED_COLORS.get(c, default))


# Map Qt keys → byte sequences sent to the PTY. Standard xterm sequences.
_KEYMAP = {
    Qt.Key.Key_Up:        b"\x1b[A",
    Qt.Key.Key_Down:      b"\x1b[B",
    Qt.Key.Key_Right:     b"\x1b[C",
    Qt.Key.Key_Left:      b"\x1b[D",
    Qt.Key.Key_Home:      b"\x1b[H",
    Qt.Key.Key_End:       b"\x1b[F",
    Qt.Key.Key_PageUp:    b"\x1b[5~",
    Qt.Key.Key_PageDown:  b"\x1b[6~",
    Qt.Key.Key_Insert:    b"\x1b[2~",
    Qt.Key.Key_Delete:    b"\x1b[3~",
    Qt.Key.Key_Backspace: b"\x7f",
    Qt.Key.Key_Tab:       b"\t",
    Qt.Key.Key_Return:    b"\r",
    Qt.Key.Key_Enter:     b"\r",
    Qt.Key.Key_Escape:    b"\x1b",
    Qt.Key.Key_F1:        b"\x1bOP",
    Qt.Key.Key_F2:        b"\x1bOQ",
    Qt.Key.Key_F3:        b"\x1bOR",
    Qt.Key.Key_F4:        b"\x1bOS",
    Qt.Key.Key_F5:        b"\x1b[15~",
    Qt.Key.Key_F6:        b"\x1b[17~",
    Qt.Key.Key_F7:        b"\x1b[18~",
    Qt.Key.Key_F8:        b"\x1b[19~",
    Qt.Key.Key_F9:        b"\x1b[20~",
    Qt.Key.Key_F10:       b"\x1b[21~",
    Qt.Key.Key_F11:       b"\x1b[23~",
    Qt.Key.Key_F12:       b"\x1b[24~",
}


class TerminalWidget(QPlainTextEdit):
    """A PTY-backed shell view. Keystrokes go to the child; output goes
    through pyte before painting."""

    started = pyqtSignal()
    exited = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUndoRedoEnabled(False)
        self.setFrameShape(self.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        f = QFont("Menlo")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(12)
        self.setFont(f)

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(_BG_DEFAULT))
        pal.setColor(QPalette.ColorRole.Text, QColor(_FG_DEFAULT))
        self.setPalette(pal)

        self._cols, self._rows = 80, 24
        self._screen = pyte.Screen(self._cols, self._rows)
        self._stream = pyte.ByteStream(self._screen)
        self._fmt_cache: dict[tuple, QTextCharFormat] = {}

        self._process = PtyProcess(self)
        self._process.output.connect(self._on_output)
        self._process.exited.connect(self._on_exited)

    # -- lifecycle -----------------------------------------------------------

    def start(self, cwd: str | None = None, argv: list[str] | None = None) -> bool:
        if self._process.is_running():
            return False
        argv = argv or [os.environ.get("SHELL", "/bin/bash"), "-l"]
        self._screen.reset()
        self.setPlainText("")
        ok = self._process.start(argv, cwd=cwd or os.environ.get("HOME"))
        if ok:
            self._update_size()
            self.started.emit()
        return ok

    def is_running(self) -> bool:
        return self._process.is_running()

    def kill(self):
        self._process.kill()

    # -- output rendering ----------------------------------------------------

    def _on_output(self, data: bytes):
        self._stream.feed(data)
        self._render_dirty()

    def _on_exited(self, code: int):
        self.exited.emit(code)

    def _render_dirty(self):
        dirty = sorted(self._screen.dirty)
        self._screen.dirty.clear()
        if not dirty:
            return
        doc = self.document()
        # Make sure the document has at least `_rows` lines.
        while doc.blockCount() < self._rows:
            tc = QTextCursor(doc)
            tc.movePosition(QTextCursor.MoveOperation.End)
            tc.insertBlock()

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        try:
            for y in dirty:
                if y >= self._rows:
                    continue
                self._render_row(cursor, y)
        finally:
            cursor.endEditBlock()

        # Park the visible cursor at pyte's cursor position.
        target = doc.findBlockByNumber(self._screen.cursor.y)
        if target.isValid():
            tc = QTextCursor(target)
            for _ in range(min(self._screen.cursor.x, self._cols)):
                tc.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(tc)

    def _render_row(self, cursor: QTextCursor, y: int):
        block = self.document().findBlockByNumber(y)
        if not block.isValid():
            return
        cursor.setPosition(block.position())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        line = self._screen.buffer[y]
        run_text: list[str] = []
        run_key = None
        for x in range(self._cols):
            cell = line[x]
            key = (cell.fg, cell.bg, cell.bold, cell.italics,
                   cell.underscore, cell.reverse)
            if key != run_key and run_text:
                cursor.insertText("".join(run_text), self._format(run_key))
                run_text = []
            run_key = key
            run_text.append(cell.data)
        if run_text:
            cursor.insertText("".join(run_text), self._format(run_key))

    def _format(self, key) -> QTextCharFormat:
        if key in self._fmt_cache:
            return self._fmt_cache[key]
        fg, bg, bold, italic, underline, reverse = key
        fmt = QTextCharFormat()
        fg_color = _color(fg, _FG_DEFAULT, bright=bold)
        bg_color = _color(bg, _BG_DEFAULT)
        if reverse:
            fg_color, bg_color = bg_color, fg_color
        fmt.setForeground(QColor(fg_color))
        if bg != "default" or reverse:
            fmt.setBackground(QColor(bg_color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if underline:
            fmt.setFontUnderline(True)
        self._fmt_cache[key] = fmt
        return fmt

    # -- input ---------------------------------------------------------------

    def keyPressEvent(self, e: QKeyEvent):
        if not self._process.is_running():
            return
        key = e.key()
        mod = e.modifiers()

        # Ctrl+letter → control byte (Ctrl+C → 0x03, Ctrl+D → 0x04, …)
        if mod & Qt.KeyboardModifier.ControlModifier:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                self._process.write(bytes([key - Qt.Key.Key_A + 1]))
                return
            if key == Qt.Key.Key_Space:
                self._process.write(b"\x00")
                return
            if key == Qt.Key.Key_BracketLeft:
                self._process.write(b"\x1b")
                return

        seq = _KEYMAP.get(key)
        if seq is not None:
            self._process.write(seq)
            return

        text = e.text()
        if text:
            self._process.write(text.encode("utf-8", errors="replace"))

    def mousePressEvent(self, event):
        # Allow selection (for copy) but always re-park caret on next render.
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_size()

    def _update_size(self):
        fm = QFontMetrics(self.font())
        char_w = max(1, fm.horizontalAdvance("M"))
        char_h = max(1, fm.height())
        cols = max(20, self.viewport().width() // char_w)
        rows = max(5, self.viewport().height() // char_h)
        if (cols, rows) == (self._cols, self._rows):
            return
        self._cols, self._rows = cols, rows
        self._screen.resize(rows, cols)
        # Reset cache — colors don't depend on size, but a fresh Screen post
        # resize will invalidate any in-flight runs.
        self._screen.dirty.update(range(rows))
        self._process.set_size(rows, cols)
        self._render_dirty()


class TerminalDock(QDockWidget):
    """Bottom dock hosting a `TerminalWidget` plus a tiny toolbar."""

    def __init__(self, parent=None):
        super().__init__("Shell", parent)
        self.setObjectName("terminal_dock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4); h.setSpacing(6)
        self.btn_restart = QToolButton(); self.btn_restart.setText("⟳ Restart")
        self.btn_kill = QToolButton(); self.btn_kill.setText("⏹ Kill")
        self.lbl_status = QLabel("idle")
        self.lbl_status.setStyleSheet("color: #888;")
        h.addWidget(self.btn_restart); h.addWidget(self.btn_kill)
        h.addStretch(); h.addWidget(self.lbl_status)
        v.addWidget(bar)

        self.term = TerminalWidget(self)
        v.addWidget(self.term, 1)
        self.setWidget(body)

        self.btn_restart.clicked.connect(self._on_restart)
        self.btn_kill.clicked.connect(self.term.kill)
        self.term.started.connect(lambda: self.lbl_status.setText("running"))
        self.term.exited.connect(self._on_exited)

    def ensure_started(self, cwd: str | None = None):
        if not self.term.is_running():
            self.term.start(cwd=cwd)

    def _on_restart(self):
        if self.term.is_running():
            self.term.kill()
        self.term.start()

    def _on_exited(self, code: int):
        self.lbl_status.setText(f"exited ({code}) · ⟳ to restart")

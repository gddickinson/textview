"""Bottom dock panel that drives a `Runner` and displays its output.

Layout: a thin toolbar (Run / Stop / Clear, language label, cwd label)
above a read-only `QPlainTextEdit` that shows ANSI-formatted stdout +
stderr, above a one-line `QLineEdit` for ad-hoc shell commands.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor, QColor
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QToolButton, QLabel, QLineEdit, QSizePolicy,
)

from .ansi_format import AnsiParser
from .runner import Runner


class RunnerPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Terminal", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.runner = Runner(self)
        self._parser_out = AnsiParser()
        self._parser_err = AnsiParser()
        self._max_blocks = 5000  # output line cap to keep UI responsive
        self._build_ui()
        self._wire()
        self.setWidget(self._root)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        self._root = QWidget()
        v = QVBoxLayout(self._root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_toolbar())
        self._output = QPlainTextEdit(readOnly=True)
        self._output.setFrameShape(self._output.Shape.NoFrame)
        self._output.setMaximumBlockCount(self._max_blocks)
        f = QFont("Menlo")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(12)
        self._output.setFont(f)
        v.addWidget(self._output, 1)
        v.addWidget(self._build_input_bar())

    def _build_toolbar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        def btn(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.btn_stop = btn("⏹ Stop", "Kill the running process (Ctrl+.)", self.stop)
        self.btn_clear = btn("🗑 Clear", "Clear output", self.clear_output)
        h.addWidget(self.btn_stop)
        h.addWidget(self.btn_clear)
        h.addStretch()

        self.lbl_cmd = QLabel("idle")
        self.lbl_cmd.setStyleSheet("color: #888;")
        h.addWidget(self.lbl_cmd)
        return bar

    def _build_input_bar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 2, 6, 4)
        h.setSpacing(4)
        h.addWidget(QLabel("$"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a shell command and press Enter…")
        self._input.returnPressed.connect(self._on_input_submitted)
        h.addWidget(self._input, 1)
        return bar

    # -- runner control ------------------------------------------------------

    def _wire(self):
        r = self.runner
        r.output.connect(self._on_output)
        r.started.connect(self._on_started)
        r.finished.connect(self._on_finished)
        r.error.connect(self._on_error)

    def run_file(self, path: str, args: list[str] | None = None):
        if not path:
            return
        self._show_self()
        suffix = (" " + " ".join(args)) if args else ""
        self._append_meta(f"\n▶ {Path(path).name}{suffix}\n")
        self.runner.run_file(path, args=args)

    def run_python_snippet(self, code: str, cwd: str | None = None):
        self._show_self()
        self._append_meta("\n▶ run selection (python)\n")
        self.runner.run_python_snippet(code, cwd=cwd)

    def run_shell(self, command: str, cwd: str | None = None):
        self._show_self()
        self.runner.run_shell(command, cwd=cwd)

    def stop(self):
        self.runner.stop()

    def clear_output(self):
        self._output.clear()

    def _show_self(self):
        if not self.isVisible():
            self.show()
        self.raise_()

    def _on_input_submitted(self):
        cmd = self._input.text()
        self._input.clear()
        if cmd.strip():
            self._append_meta(f"\n$ {cmd}\n")
            self.runner.run_shell(cmd)

    # -- output rendering ----------------------------------------------------

    def _on_output(self, text: str, stream: str):
        parser = self._parser_out if stream == "stdout" else self._parser_err
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for chunk, fmt in parser.feed(text):
            if stream == "stderr" and not fmt.foreground().color().isValid():
                # No explicit color from ANSI? give stderr a subtle red tint.
                fmt.setForeground(QColor("#ff7b7b"))
            cursor.insertText(chunk, fmt)
        self._output.setTextCursor(cursor)

    def _on_started(self, line: str):
        self.lbl_cmd.setText(line)

    def _on_finished(self, code: int, status: int):
        marker = "✓" if code == 0 else "✗"
        self._append_meta(f"\n{marker} exited with code {code}\n", code != 0)
        self.lbl_cmd.setText(f"idle  ·  last exit: {code}")

    def _on_error(self, msg: str):
        self._append_meta(f"\n⚠ {msg}\n", error=True)

    def _append_meta(self, text: str, error: bool = False):
        from PyQt6.QtGui import QTextCharFormat
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#ff7b7b") if error else QColor("#88c0d0"))
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)

"""Long-operation status indicator.

Shows a small spinning ASCII glyph + a message in the status bar while a
long-running task is in flight (workspace indexing, query, file load).
Use as a context manager:

    with BusyIndicator(window, "Indexing…"):
        index.build()

The spinner runs on a `QTimer` so it animates without blocking. If the
operation completes faster than 250 ms, no message is shown — keeps the
UI quiet for snappy operations.
"""
from __future__ import annotations
from PyQt6.QtCore import QObject, QTimer


_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class BusyIndicator(QObject):
    """Status-bar spinner. Use as a context manager."""

    def __init__(self, window, message: str, *, delay_ms: int = 250,
                 interval_ms: int = 80):
        # Accept non-QObject windows (test fakes) by falling back to None.
        super().__init__(window if isinstance(window, QObject) else None)
        self.window = window
        self.message = message
        self._frame = 0
        self._delay = delay_ms
        self._interval = interval_ms
        # QTimer parent is `self` (a real QObject regardless of `window`).
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(self._interval)
        self._spin_timer.timeout.connect(self._tick)
        self._delay_timer = QTimer(self); self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._start_spinning)
        self._active = False

    def __enter__(self):
        self._delay_timer.start(self._delay)
        return self

    def __exit__(self, *exc):
        self._delay_timer.stop()
        if self._active:
            self._spin_timer.stop()
            try: self.window.statusBar().clearMessage()
            except Exception: pass
            self._active = False

    def _start_spinning(self):
        self._active = True
        self._tick()
        self._spin_timer.start()

    def _tick(self):
        try:
            self.window.statusBar().showMessage(
                f"{_FRAMES[self._frame]}  {self.message}")
        except Exception:
            pass
        self._frame = (self._frame + 1) % len(_FRAMES)

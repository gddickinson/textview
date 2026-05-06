"""CodeViewer: cursor-pause hover signal (timer + gating)."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt, QEventLoop, QDeadlineTimer
from PyQt6.QtGui import QMouseEvent

from src.viewer import CodeViewer


def _move(widget, x: float, y: float):
    """Synthesize a MouseMove event at viewport-relative (x, y)."""
    pos = QPointF(x, y)
    ev = QMouseEvent(
        QMouseEvent.Type.MouseMove, pos, pos,
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # The viewport receives mouse events for QPlainTextEdit subclasses.
    widget.mouseMoveEvent(ev)


def _wait_for_signal(qapp, captured, timeout_ms=2000):
    deadline = QDeadlineTimer(timeout_ms)
    while not deadline.hasExpired() and not captured:
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def test_default_state_is_disabled(qapp):
    v = CodeViewer()
    assert v._hover_enabled is False


def test_enable_then_pause_emits_signal(qapp):
    v = CodeViewer(); v.setPlainText("hello world\nfoo bar\n")
    v.set_hover_pause_enabled(True)
    captured = []
    v.cursor_paused.connect(lambda p: captured.append(p))
    # Shrink debounce so the test is fast.
    v._hover_timer.setInterval(50)
    _move(v, 30, 10)
    _wait_for_signal(qapp, captured)
    assert len(captured) == 1
    assert isinstance(captured[0], QPoint)


def test_subsequent_move_resets_debounce(qapp):
    v = CodeViewer(); v.setPlainText("abc def ghi\n")
    v.set_hover_pause_enabled(True)
    v._hover_timer.setInterval(80)
    captured = []
    v.cursor_paused.connect(lambda p: captured.append(p))
    _move(v, 10, 10)
    # Move again before the timer fires — should restart, no emit yet.
    qapp.processEvents()
    _move(v, 20, 10)
    qapp.processEvents()
    # Now wait for one fire.
    _wait_for_signal(qapp, captured)
    # Exactly one emit (the latest pause), not two.
    assert len(captured) == 1


def test_disabled_does_not_emit(qapp):
    v = CodeViewer(); v.setPlainText("xx\n")
    captured = []
    v.cursor_paused.connect(lambda p: captured.append(p))
    v._hover_timer.setInterval(40)
    _move(v, 10, 10)  # no set_hover_pause_enabled(True)
    qapp.processEvents()
    deadline = QDeadlineTimer(150)
    while not deadline.hasExpired():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
    assert captured == []


def test_disable_after_enable_stops_pending_timer(qapp):
    v = CodeViewer(); v.setPlainText("xx\n")
    v.set_hover_pause_enabled(True)
    v._hover_timer.setInterval(50)
    captured = []
    v.cursor_paused.connect(lambda p: captured.append(p))
    _move(v, 10, 10)
    v.set_hover_pause_enabled(False)  # cancel mid-debounce
    deadline = QDeadlineTimer(150)
    while not deadline.hasExpired():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
    assert captured == []

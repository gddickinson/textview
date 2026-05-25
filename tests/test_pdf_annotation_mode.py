"""Coverage for the mouse-driven annotation UX on PdfViewer.

The viewer's coordinate-conversion + mode state machine can be
tested without mocking QPdfView itself, because every interesting
piece is exposed as a method (`_viewport_to_pdf`, `_normalize_rect_px`,
`set_annotation_mode`, `_annotation_mouse_*`).

The end-to-end "real drag fires the signal with correct PDF coords"
path is covered by a synthetic test that monkeypatches the helpers
to bypass the real QPdfView document."""
from __future__ import annotations

import pytest
from pathlib import Path
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt, QPointF, QEvent


# ---------- normalize_rect_px (pure helper) -----------------------------

def test_normalize_rect_top_left_to_bottom_right(qapp):
    from src.pdf_viewer import PdfViewer
    r = PdfViewer._normalize_rect_px(QPoint(10, 20), QPoint(60, 80))
    assert r == QRect(10, 20, 50, 60)


def test_normalize_rect_bottom_right_to_top_left(qapp):
    """Dragging from BR → TL still produces a top-left-origin rect."""
    from src.pdf_viewer import PdfViewer
    r = PdfViewer._normalize_rect_px(QPoint(60, 80), QPoint(10, 20))
    assert r == QRect(10, 20, 50, 60)


def test_normalize_rect_zero_size(qapp):
    from src.pdf_viewer import PdfViewer
    r = PdfViewer._normalize_rect_px(QPoint(5, 5), QPoint(5, 5))
    assert r == QRect(5, 5, 0, 0)


# ---------- ALL_MODES taxonomy ------------------------------------------

def test_mode_taxonomy(qapp):
    from src.pdf_viewer import PdfViewer
    # Every accepted mode goes into exactly one bucket.
    assert "off" in PdfViewer.ALL_MODES
    assert set(PdfViewer.POINT_MODES).isdisjoint(set(PdfViewer.RECT_MODES))
    assert ("sticky" in PdfViewer.POINT_MODES)
    for m in ("freetext", "highlight", "underline", "strikeout",
              "rect", "circle"):
        assert m in PdfViewer.RECT_MODES


# ---------- set_annotation_mode -----------------------------------------

def test_set_mode_starts_off(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    assert v.annotation_mode() == "off"


def test_set_mode_arms(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("highlight", color="#abcdef")
    assert v.annotation_mode() == "highlight"
    assert v.annotation_color() == "#abcdef"


def test_set_mode_off_resets_state(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("rect", "#FF0000")
    v.set_annotation_mode("off")
    assert v.annotation_mode() == "off"


def test_unknown_mode_raises(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    with pytest.raises(ValueError):
        v.set_annotation_mode("flamingo")


def test_set_annotation_color_persists(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_color("#12ab34")
    v.set_annotation_mode("highlight")
    assert v.annotation_color() == "#12ab34"


# ---------- annotation_mode_changed signal ------------------------------

def test_mode_changed_signal_fires(qapp, qtbot=None):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    seen = []
    v.annotation_mode_changed.connect(lambda m: seen.append(m))
    v.set_annotation_mode("freetext", "#000")
    v.set_annotation_mode("off")
    assert seen == ["freetext", "off"]


# ---------- _viewport_to_pdf with no document ---------------------------

def test_viewport_to_pdf_no_doc_returns_none(qapp):
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    assert v._viewport_to_pdf(QPoint(50, 50)) is None


# ---------- end-to-end: monkeypatched coord conversion ------------------

def test_drag_emits_committed_signal(qapp, monkeypatch):
    """Synthetic drag → annotation_committed fires once with the
    correct mode / page / rect / color. We monkeypatch
    `_viewport_to_pdf` to bypass needing a real QPdfDocument."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("highlight", "#FFFF00")

    # Pretend the viewport directly maps to PDF coords at scale 1.
    def fake_v2p(self, pt):
        # Page 0, identity map; both points must be inside the
        # "page" rectangle 0..1000.
        if 0 <= pt.x() <= 1000 and 0 <= pt.y() <= 1000:
            return 0, float(pt.x()), float(pt.y())
        return None
    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf", fake_v2p)

    events = []
    v.annotation_committed.connect(
        lambda mode, page, rect, color: events.append((mode, page, rect, color)))

    # Simulate press → move → release without going through Qt's event
    # loop. The mouse handlers return True if they consumed the event.
    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(100, 200), QPointF(100, 200),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QEvent.Type.MouseMove,
                        QPointF(300, 400), QPointF(300, 400),
                        Qt.MouseButton.NoButton,
                        Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(300, 400), QPointF(300, 400),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    assert v._annotation_mouse_press(press) is True
    assert v._annotation_mouse_move(move) is True
    assert v._annotation_mouse_release(release) is True

    assert len(events) == 1
    mode, page, rect, color = events[0]
    assert mode == "highlight"
    assert page == 0
    # Rect is (x, y, w, h) in PDF points with top-left origin.
    assert rect == (100.0, 200.0, 200.0, 200.0)
    assert color == "#FFFF00"


def test_drag_reverse_direction_yields_normalized_rect(qapp, monkeypatch):
    """Drag from bottom-right to top-left still produces a
    top-left-origin PDF rect."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("rect", "#FF0000")

    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf",
        lambda self, p: (0, float(p.x()), float(p.y())))

    events = []
    v.annotation_committed.connect(
        lambda mode, page, rect, color: events.append(rect))

    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(300, 400), QPointF(300, 400),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(100, 200), QPointF(100, 200),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    v._annotation_mouse_press(press)
    v._annotation_mouse_release(release)

    assert events == [(100.0, 200.0, 200.0, 200.0)]


def test_click_in_point_mode_emits_signal(qapp, monkeypatch):
    """In sticky mode, a click (no drag) still fires
    annotation_committed with a 1×1 rect at the click point."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("sticky", "#FFFF00")
    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf",
        lambda self, p: (3, float(p.x()), float(p.y())))

    events = []
    v.annotation_committed.connect(
        lambda mode, page, rect, color: events.append((mode, page, rect)))

    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(50, 50), QPointF(50, 50),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(50, 50), QPointF(50, 50),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    v._annotation_mouse_press(press)
    v._annotation_mouse_release(release)

    assert events == [("sticky", 3, (50.0, 50.0, 1.0, 1.0))]


def test_tiny_drag_rejected(qapp, monkeypatch):
    """Drag with < 1 PDF point in width or height is treated as
    accidental and no signal fires."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("rect", "#000")
    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf",
        lambda self, p: (0, float(p.x()), float(p.y())))

    events = []
    v.annotation_committed.connect(
        lambda mode, page, rect, color: events.append(rect))
    mode_msgs = []
    v.annotation_mode_changed.connect(lambda m: mode_msgs.append(m))

    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(100, 100), QPointF(100, 100),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(100, 100), QPointF(100, 100),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    v._annotation_mouse_press(press)
    v._annotation_mouse_release(release)
    assert events == []
    # An informational status message was routed through the same signal.
    assert any("too small" in m for m in mode_msgs)


def test_click_outside_page_rejected(qapp, monkeypatch):
    """A click whose viewport→PDF maps to outside the page → no signal,
    but a friendly status message gets routed."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("sticky", "#FFFF00")
    # Return None to simulate "outside the page."
    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf",
        lambda self, p: None)

    events = []
    v.annotation_committed.connect(
        lambda *a: events.append(a))
    msgs = []
    v.annotation_mode_changed.connect(lambda m: msgs.append(m))

    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(0, 0), QPointF(0, 0),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(0, 0), QPointF(0, 0),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    v._annotation_mouse_press(press)
    v._annotation_mouse_release(release)
    assert events == []
    assert any("outside the page" in m for m in msgs)


def test_drag_across_pages_rejected(qapp, monkeypatch):
    """Press lands on page 0, release on page 1 → no signal,
    informational message instead."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    v.set_annotation_mode("highlight", "#FFFF00")

    # The first call returns page 0, the second returns page 1.
    calls = {"n": 0}
    def fake(self, p):
        calls["n"] += 1
        return (calls["n"] - 1, float(p.x()), float(p.y()))
    monkeypatch.setattr(PdfViewer, "_viewport_to_pdf", fake)

    events = []
    v.annotation_committed.connect(lambda *a: events.append(a))
    msgs = []
    v.annotation_mode_changed.connect(lambda m: msgs.append(m))

    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(100, 100), QPointF(100, 100),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease,
                           QPointF(300, 300), QPointF(300, 300),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    v._annotation_mouse_press(press)
    v._annotation_mouse_release(release)
    assert events == []
    assert any("spanned two pages" in m for m in msgs)


def test_mode_off_means_no_handler_consumes(qapp):
    """When mode is off, all three helpers return False so the base
    class gets to run (links / text selection still work)."""
    from src.pdf_viewer import PdfViewer
    v = PdfViewer()
    press = QMouseEvent(QEvent.Type.MouseButtonPress,
                         QPointF(10, 10), QPointF(10, 10),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
    assert v._annotation_mouse_press(press) is False
    assert v._annotation_mouse_move(press) is False
    assert v._annotation_mouse_release(press) is False

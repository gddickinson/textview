"""PdfViewer — `QPdfView` with link-click dispatch, search wiring, a
context menu for copying page text, and **mouse-driven annotation
mode** (v3.5 phase 2b).

Annotation modes:
    "sticky"  — click → place sticky-note pin
    "freetext"— drag → place free-text box (handler prompts for text)
    "highlight" / "underline" / "strikeout"  — drag → over a region
    "rect" / "circle" — drag → draw shape outline

State machine:
    set_annotation_mode(mode, color) → arms mouse handlers
    Esc keypress or `set_annotation_mode("off")` → cancels.
    On a completed click / drag, the viewer emits
    `annotation_committed(mode, page_index, rect_pdf, color)` where
    `rect_pdf = (x, y, width, height)` in PDF points (top-left origin
    in MuPDF convention). For click-only modes the rect is a 1×1 box
    at the click point; the bridge picks (x, y) out for the sticky
    handler.

Coordinate conversion (single-page mode assumption):
    pdf_x = (viewport_x + h_scroll) / zoom_factor
    pdf_y = (viewport_y + v_scroll) / zoom_factor
Multi-page mode would need the per-page Y-offset within the document
which QPdfView doesn't expose cleanly — the menu-side action
auto-switches to single-page before enabling annotation mode.
"""
from PyQt6.QtCore import Qt, QPointF, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QCursor
from PyQt6.QtPdf import QPdfLinkModel, QPdfSearchModel
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import QMenu, QApplication, QRubberBand


class PdfViewer(QPdfView):
    """QPdfView with explicit link-click + text-copy support, plus
    mouse-driven annotation mode (v3.5 phase 2b).

    Qt 6.5+ has built-in link handling, but we wire it up ourselves too so
    behavior is deterministic across Qt builds.
    """

    # Annotation modes accepted by `set_annotation_mode`. "off" disables.
    POINT_MODES = ("sticky",)
    RECT_MODES = ("freetext", "highlight", "underline",
                  "strikeout", "rect", "circle")
    ALL_MODES = POINT_MODES + RECT_MODES + ("off",)

    # Emitted when a click / drag completes in annotation mode.
    # Args: (mode, page_index, rect_pdf, color_hex). `rect_pdf` is
    # (x, y, w, h) in PDF points (top-left origin, MuPDF convention).
    annotation_committed = pyqtSignal(str, int, tuple, str)
    # Emitted when the active mode changes — host can update the
    # status bar.
    annotation_mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_model = QPdfLinkModel(self)
        self._search_model = QPdfSearchModel(self)
        self.setSearchModel(self._search_model)
        self.setMouseTracking(True)

        # Annotation-mode state.
        self._annot_mode: str = "off"
        self._annot_color: str = "#FFFF00"
        self._drag_start: QPoint | None = None
        self._rubber_band: QRubberBand | None = None
        # Save the prior cursor so we can restore on mode exit.
        self._prior_cursor = self.viewport().cursor()

    def setDocument(self, doc):
        super().setDocument(doc)
        self._link_model.setDocument(doc)
        self._search_model.setDocument(doc)

    # -- search -------------------------------------------------------------

    def _result_count(self) -> int:
        doc = self.document()
        if not doc:
            return 0
        return sum(len(self._search_model.resultsOnPage(p))
                   for p in range(doc.pageCount()))

    def find(self, query: str) -> int:
        """Set the active search string; jump to the first match. QPdfView
        shows highlight rectangles automatically once searchString is set.
        """
        self._search_model.setSearchString(query or "")
        if not query:
            return 0
        total = self._result_count()
        if total:
            self.setCurrentSearchResultIndex(0)
        return total

    def find_next(self, direction: int = 1):
        total = self._result_count()
        if total <= 0:
            return
        idx = max(0, self.currentSearchResultIndex())
        self.setCurrentSearchResultIndex((idx + direction) % total)

    # -- right-click → text copy --------------------------------------------

    def contextMenuEvent(self, event):
        doc = self.document()
        if doc is None:
            return super().contextMenuEvent(event)
        page = self.pageNavigator().currentPage() if self.pageNavigator() else 0
        menu = QMenu(self)
        a_page = menu.addAction(f"Copy text on page {page + 1}")
        a_all = menu.addAction("Copy text on all pages")
        chosen = menu.exec(event.globalPos())
        if chosen is a_page:
            sel = doc.getAllText(page)
            if sel and sel.isValid():
                QApplication.clipboard().setText(sel.text())
        elif chosen is a_all:
            chunks = []
            for p in range(doc.pageCount()):
                s = doc.getAllText(p)
                if s and s.isValid():
                    chunks.append(s.text())
            QApplication.clipboard().setText("\n\n".join(chunks))

    # -- link clicks --------------------------------------------------------

    def _hit_link(self, viewport_pos):
        """Map a viewport-coordinate click to a QPdfLink, or None."""
        doc = self.document()
        if doc is None:
            return None
        nav = self.pageNavigator()
        page = nav.currentPage() if nav else 0
        page_size_pt = doc.pagePointSize(page)
        scale = self.zoomFactor() or 1.0
        h = self.horizontalScrollBar().value()
        v = self.verticalScrollBar().value()
        x = (viewport_pos.x() + h) / scale
        y = (viewport_pos.y() + v) / scale
        if not (0 <= x <= page_size_pt.width() and 0 <= y <= page_size_pt.height()):
            return None
        self._link_model.setPage(page)
        link = self._link_model.linkAt(QPointF(x, y))
        return link if link.isValid() else None

    # -- annotation mode: public API ---------------------------------------

    def annotation_mode(self) -> str:
        return self._annot_mode

    def annotation_color(self) -> str:
        return self._annot_color

    def set_annotation_color(self, color_hex: str) -> None:
        """Pre-set the color used for the next annotation."""
        self._annot_color = color_hex or "#FFFF00"

    def set_annotation_mode(self, mode: str, color: str | None = None) -> None:
        """Arm the viewer for an annotation. Passing `"off"` (or
        `None`) cancels the active mode and restores the I-beam
        cursor. Any in-progress drag is dropped.
        """
        mode = (mode or "off").lower()
        if mode not in self.ALL_MODES:
            raise ValueError(f"unknown annotation mode: {mode!r}")
        if mode == "off":
            self._exit_annotation_mode()
            return
        self._annot_mode = mode
        if color is not None: self._annot_color = color
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.annotation_mode_changed.emit(mode)

    def _exit_annotation_mode(self) -> None:
        self._annot_mode = "off"
        self._drag_start = None
        if self._rubber_band is not None:
            self._rubber_band.hide()
        self.viewport().setCursor(self._prior_cursor)
        self.annotation_mode_changed.emit("off")

    # -- annotation mode: coord conversion ---------------------------------

    def _viewport_to_pdf(self, vp_pos) -> tuple[int, float, float] | None:
        """Map a viewport-coordinate point to `(page_index, pdf_x,
        pdf_y)` in MuPDF top-left coords. Returns `None` for clicks
        outside the current page's rectangle."""
        doc = self.document()
        if doc is None:
            return None
        nav = self.pageNavigator()
        page = nav.currentPage() if nav else 0
        page_size_pt = doc.pagePointSize(page)
        scale = self.zoomFactor() or 1.0
        h = self.horizontalScrollBar().value()
        v = self.verticalScrollBar().value()
        x = (vp_pos.x() + h) / scale
        y = (vp_pos.y() + v) / scale
        if not (0 <= x <= page_size_pt.width()
                and 0 <= y <= page_size_pt.height()):
            return None
        return page, float(x), float(y)

    @staticmethod
    def _normalize_rect_px(start: QPoint, end: QPoint) -> QRect:
        """Force a top-left-origin rectangle regardless of drag direction.
        Pure function so tests can exercise it without QPdfView."""
        x = min(start.x(), end.x())
        y = min(start.y(), end.y())
        w = abs(end.x() - start.x())
        h = abs(end.y() - start.y())
        return QRect(x, y, w, h)

    # -- annotation mode: mouse handlers -----------------------------------

    def _annotation_mouse_press(self, event) -> bool:
        """Return True if the event was handled by annotation mode
        (caller should `event.accept()` and stop). Returns False to
        let the base class run."""
        if self._annot_mode == "off":
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._drag_start = event.position().toPoint()
        if self._annot_mode in self.RECT_MODES:
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(
                    QRubberBand.Shape.Rectangle, self.viewport())
            self._rubber_band.setGeometry(QRect(self._drag_start, QSize(0, 0)))
            self._rubber_band.show()
        event.accept()
        return True

    def _annotation_mouse_move(self, event) -> bool:
        if (self._annot_mode == "off"
                or self._drag_start is None
                or self._rubber_band is None):
            return False
        if self._annot_mode in self.RECT_MODES:
            self._rubber_band.setGeometry(
                self._normalize_rect_px(self._drag_start,
                                         event.position().toPoint()))
            event.accept()
            return True
        return False

    def _annotation_mouse_release(self, event) -> bool:
        if self._annot_mode == "off" or self._drag_start is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        end = event.position().toPoint()
        start = self._drag_start
        mode = self._annot_mode
        color = self._annot_color
        self._drag_start = None
        if self._rubber_band is not None:
            self._rubber_band.hide()

        if mode in self.POINT_MODES:
            # Click annotations — use the press point as the anchor.
            pt = self._viewport_to_pdf(start)
            if pt is None:
                self.annotation_mode_changed.emit(
                    f"{mode}: click was outside the page")
                event.accept()
                return True
            page, x, y = pt
            # Convey as a 1×1 rect so the signal shape stays uniform;
            # the bridge picks (x, y) out for click-only annotations.
            self.annotation_committed.emit(mode, page, (x, y, 1.0, 1.0), color)
            event.accept()
            return True

        # Rect annotations: convert both endpoints, then build the
        # PDF-coord rect.
        a = self._viewport_to_pdf(start)
        b = self._viewport_to_pdf(end)
        if a is None or b is None:
            self.annotation_mode_changed.emit(
                f"{mode}: drag must be inside the page")
            event.accept()
            return True
        if a[0] != b[0]:
            # Drag spanned two pages — refuse rather than silently
            # snapping to one.
            self.annotation_mode_changed.emit(
                f"{mode}: drag spanned two pages — cancelled")
            event.accept()
            return True
        page, ax, ay = a
        _, bx, by = b
        x = min(ax, bx); y = min(ay, by)
        w = abs(bx - ax); h = abs(by - ay)
        if w < 1 or h < 1:
            # Tiny / zero-area drag — also reject as accidental.
            self.annotation_mode_changed.emit(
                f"{mode}: drag too small")
            event.accept()
            return True
        self.annotation_committed.emit(mode, page, (x, y, w, h), color)
        event.accept()
        return True

    # -- key + mouse routing -----------------------------------------------

    def keyPressEvent(self, event):
        # Esc cancels annotation mode without committing.
        if (event.key() == Qt.Key.Key_Escape
                and self._annot_mode != "off"):
            self._exit_annotation_mode()
            event.accept(); return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._annotation_mouse_press(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._annotation_mouse_move(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._annotation_mouse_release(event):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            link = self._hit_link(event.position().toPoint())
            if link is not None:
                url = link.url()
                if url.isValid() and not url.isEmpty():
                    QDesktopServices.openUrl(url)
                    event.accept()
                    return
                if link.page() >= 0 and self.pageNavigator() is not None:
                    self.pageNavigator().jump(link)
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

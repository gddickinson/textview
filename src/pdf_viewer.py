"""PdfViewer — `QPdfView` with link-click dispatch, search wiring, and a
context menu for copying page text.
"""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtPdf import QPdfLinkModel, QPdfSearchModel
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import QMenu, QApplication


class PdfViewer(QPdfView):
    """QPdfView with explicit link-click + text-copy support.

    Qt 6.5+ has built-in link handling, but we wire it up ourselves too so
    behavior is deterministic across Qt builds.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_model = QPdfLinkModel(self)
        self._search_model = QPdfSearchModel(self)
        self.setSearchModel(self._search_model)
        self.setMouseTracking(True)

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

    def mouseReleaseEvent(self, event):
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

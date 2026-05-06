"""Native PDF rendering via QtPdf.

`PdfController` owns a `QPdfDocument` and knows how to apply our
display-settings vocabulary (page mode, zoom mode, custom zoom factor) to a
`QPdfView`. The MainWindow holds one controller and pushes it into the
viewer's `QPdfView` whenever a PDF is loaded or settings change.

It can also rasterize pages directly to a `QImage` without a widget, which
the headless screenshot path uses (no QPdfView, no offscreen-renderer
crashes).
"""
from PyQt6.QtCore import QSize
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView


_PAGE_MODE_MAP = {
    "single": QPdfView.PageMode.SinglePage,
    "multi": QPdfView.PageMode.MultiPage,
}

_ZOOM_MODE_MAP = {
    "fit_width": QPdfView.ZoomMode.FitToWidth,
    "fit_page": QPdfView.ZoomMode.FitInView,
    "custom": QPdfView.ZoomMode.Custom,
}


class PdfController:
    """Loads a PDF into a QPdfDocument and applies settings to a QPdfView."""

    def __init__(self):
        self.doc: QPdfDocument | None = None
        self.path: str | None = None
        # Track the most recent view we attached to so we can tell it to
        # release the doc *before* we drop the controller's Python reference.
        # Without this, QPdfView keeps a dangling C++ pointer at the freed
        # doc and crashes inside QPdfLinkModel::setDocument's disconnect on
        # the next setDocument call (segfault on tab close).
        self._attached_view: QPdfView | None = None

    def load(self, path: str) -> bool:
        """Load a PDF from disk. Returns True on success."""
        self._detach_view()
        doc = QPdfDocument(None)
        status = doc.load(str(path))
        # In PyQt6, status is QPdfDocument.Error.None_ on success.
        ok = status == QPdfDocument.Error.None_
        if ok:
            self.doc = doc
            self.path = str(path)
        return ok

    def clear(self):
        self._detach_view()
        self.doc = None
        self.path = None

    def _detach_view(self):
        v = self._attached_view
        if v is None or self.doc is None:
            return
        try:
            v.setDocument(None)
        except RuntimeError:
            # View was deleted on the C++ side already; nothing to detach.
            pass
        self._attached_view = None

    def attach(self, view: QPdfView, page_mode="multi", zoom_mode="fit_width", zoom=1.0):
        """Bind the document to a QPdfView and apply mode/zoom settings."""
        if self.doc is None:
            return
        view.setDocument(self.doc)
        self._attached_view = view
        view.setPageMode(_PAGE_MODE_MAP.get(page_mode, QPdfView.PageMode.MultiPage))
        view.setZoomMode(_ZOOM_MODE_MAP.get(zoom_mode, QPdfView.ZoomMode.FitToWidth))
        if zoom_mode == "custom":
            view.setZoomFactor(max(0.1, float(zoom)))

    def page_count(self) -> int:
        return self.doc.pageCount() if self.doc else 0

    def render_page_image(self, page_index: int, dpi: int = 150):
        """Rasterize a single page to a QImage at the given DPI.

        Goes straight through QPdfDocument and never touches a widget, so it
        works fine in offscreen / headless mode.
        """
        if self.doc is None:
            return None
        if page_index < 0 or page_index >= self.doc.pageCount():
            return None
        size_pt = self.doc.pagePointSize(page_index)  # 1 pt = 1/72 inch
        w = max(1, int(size_pt.width() * dpi / 72.0))
        h = max(1, int(size_pt.height() * dpi / 72.0))
        return self.doc.render(page_index, QSize(w, h))

"""Export the displayed content to various formats."""
from pathlib import Path

from PyQt6.QtCore import QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from .renderers import escape_to_html


def export_html_plain(text, path, theme):
    """Export plain text wrapped in a themed HTML <pre>."""
    Path(path).write_text(escape_to_html(text, theme), encoding="utf-8")


def export_html_rendered(html_content, path):
    Path(path).write_text(html_content, encoding="utf-8")


def export_pdf(viewer_widget, path):
    """Print the active viewer's QTextDocument to a PDF."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    layout = QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait,
        QMarginsF(15, 15, 15, 15),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(layout)
    viewer_widget.document().print(printer)


def export_plain(text, path):
    Path(path).write_text(text, encoding="utf-8")


def export_markdown(text, path):
    Path(path).write_text(text, encoding="utf-8")


def export_rtf(text, path):
    """Minimal RTF: escape braces/backslashes and use \\par for newlines."""
    body = (
        text.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\n", "\\par\n")
    )
    rtf = "{\\rtf1\\ansi\\deff0\n" + body + "\n}"
    Path(path).write_text(rtf, encoding="ascii", errors="replace")


def export_image(viewer_widget, path):
    """Save a snapshot of the viewer's current viewport as an image."""
    pix = viewer_widget.viewport().grab()
    pix.save(str(path))


def screenshot_widget(widget, path):
    """Grab any widget (whole frame, not just viewport) to an image file."""
    pix = widget.grab()
    return bool(pix.save(str(path)))


def render_pdf_page(pdf_controller, page_index, path, dpi=150):
    """Rasterize a single PDF page to an image file.

    Uses `QPdfDocument.render` so it doesn't need an active QPdfView — works
    headlessly. Returns True on success.
    """
    img = pdf_controller.render_page_image(page_index, dpi)
    if img is None or img.isNull():
        return False
    return bool(img.save(str(path)))


def render_pdf_pages(pdf_controller, dir_path, dpi=150, prefix="page", fmt="png"):
    """Rasterize all pages of a loaded PDF into a directory.

    Returns the list of paths written.
    """
    out_dir = Path(dir_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = pdf_controller.page_count()
    if n == 0:
        return []
    digits = max(2, len(str(n)))
    written = []
    for i in range(n):
        out = out_dir / f"{prefix}_{i + 1:0{digits}d}.{fmt}"
        if render_pdf_page(pdf_controller, i, out, dpi):
            written.append(str(out))
    return written


def print_document(viewer_widget, parent=None):
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, parent)
    if dialog.exec():
        viewer_widget.document().print(printer)

"""Action handlers for "create an editable copy of this PDF."

Two routes, both producing a file you can edit in TextView, then
re-export to PDF via the existing pipelines:

1. **Convert to Markdown…** — opens the resulting `.md` in a new
   tab. Edit it in TextView's existing Markdown editor, then
   **File → Save As → .pdf** (uses the markdown → HTML → PDF
   path from v3.4 save-as conversions) or
   **Save As → .docx** for Word output.

2. **Convert to DOCX…** — produces a Word document with
   layout-preserving conversion. Open in Word / LibreOffice / TextView.

Both routes deliberately do NOT try to round-trip back through a
"PDF → LaTeX" path; no such open-source tool produces compilable
LaTeX in 2026.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QMessageBox, QInputDialog

from .pdf_actions import _require_pdf
from .pdf_reconstruct import (
    PdfReconstructError, pdf_to_markdown, pdf_to_docx,
)


def _handle_error(window, exc: PdfReconstructError):
    QMessageBox.warning(window, "PDF reconstruction failed", str(exc))


def convert_to_markdown(window) -> None:
    """**PDF → Convert to editable Markdown…** flow."""
    if not _require_pdf(window): return
    ret = QMessageBox.question(
        window, "Convert PDF → Markdown",
        ("Convert the open PDF to Markdown for editing?\n\n"
         "Layout details (precise positioning, font choice, page "
         "breaks) are lost — the result is a clean, editable "
         "Markdown file. Re-export via File → Save As → .pdf or "
         ".docx once you've finished editing."),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if ret != QMessageBox.StandardButton.Yes: return
    try:
        out = pdf_to_markdown(window._current_path)
    except PdfReconstructError as e:
        _handle_error(window, e); return
    window.statusBar().showMessage(
        f"Converted PDF → Markdown → {Path(out).name}", 6000)
    window.open_file(out, confirm=False)


def convert_to_docx(window) -> None:
    """**PDF → Convert to editable DOCX…** flow."""
    if not _require_pdf(window): return
    ret = QMessageBox.question(
        window, "Convert PDF → DOCX",
        ("Convert the open PDF to a Word document?\n\n"
         "Layout preservation is good for plain prose + tables + "
         "images. Multi-column documents, footnotes, math, and "
         "rotated text often come out badly. Open the result in "
         "Word / LibreOffice / TextView to edit."),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if ret != QMessageBox.StandardButton.Yes: return
    try:
        out = pdf_to_docx(window._current_path)
    except PdfReconstructError as e:
        _handle_error(window, e); return
    window.statusBar().showMessage(
        f"Converted PDF → DOCX → {Path(out).name}", 6000)
    window.open_file(out, confirm=False)

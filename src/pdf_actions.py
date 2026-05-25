"""PDF-editing action handlers, bridging MainWindow to `pdf_editor`.

Each handler:
  1. Confirms a PDF is currently open (`_current_format == "pdf"`).
  2. Reads the current page from `pdf_view.pageNavigator()`.
  3. Prompts the user for any extra input (page range, second PDF
     path, rotation degrees).
  4. Calls into `pdf_editor` with a sibling `*-edited.pdf` output by
     default, then opens the result in a new tab.

Held separately from `pdf_renderer.py` (which owns viewer state) and
from `app.py` (which is at its line cap) so the editing surface can
grow without bloating either.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .pdf_editor import (
    PdfEditError, parse_page_range, derive_output_path,
    rotate_pages, delete_pages, extract_pages,
    merge_pdfs, insert_blank_page,
)


# ----------------------------------------------------------- internals --

def _require_pdf(window) -> bool:
    """Status-bar an error if no PDF is open. Returns True iff a PDF
    is open."""
    if window._current_format != "pdf" or not window._current_path:
        window.statusBar().showMessage(
            "PDF edit: no PDF file is open.", 5000)
        return False
    return True


def _current_page(window) -> int:
    """0-based current page index, or 0 if no navigator yet."""
    try:
        nav = window.viewer.pdf_view.pageNavigator()
        return int(nav.currentPage()) if nav else 0
    except Exception:
        return 0


def _page_count(window) -> int:
    try:
        return int(window._pdf.page_count())
    except Exception:
        return 0


def _suggest_output(window) -> str:
    """Sibling `*-edited.pdf`, deduped if already taken."""
    return derive_output_path(window._current_path)


def _finish(window, output_path: str, summary: str) -> None:
    """Open the produced PDF in a new tab and surface a status note."""
    window.statusBar().showMessage(summary, 6000)
    window.open_file(output_path, confirm=False)


def _handle_edit_error(window, exc: PdfEditError, title: str = "PDF edit failed"):
    QMessageBox.warning(window, title, str(exc))


# ----------------------------------------------------------- actions --

def rotate_current_page(window, degrees: int) -> None:
    if not _require_pdf(window): return
    cur = _current_page(window)
    out = _suggest_output(window)
    try:
        n = rotate_pages(window._current_path, out, [cur], degrees)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out, f"Rotated page {cur + 1} by {degrees}° → {Path(out).name}")


def delete_current_page(window) -> None:
    if not _require_pdf(window): return
    cur = _current_page(window)
    total = _page_count(window)
    if total <= 1:
        window.statusBar().showMessage(
            "Refusing to delete the only page in this PDF.", 5000)
        return
    ret = QMessageBox.question(
        window, "Delete page",
        f"Delete page {cur + 1} of {total}?\n\n"
        f"The original file is left untouched; the edited copy is "
        f"saved to {Path(_suggest_output(window)).name}.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if ret != QMessageBox.StandardButton.Yes: return
    out = _suggest_output(window)
    try:
        n = delete_pages(window._current_path, out, [cur])
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out, f"Deleted page {cur + 1} → {n} pages remain in {Path(out).name}")


def extract_pages_dialog(window) -> None:
    """Prompt for a range like `1-3,7,10-end` and write the slice."""
    if not _require_pdf(window): return
    total = _page_count(window)
    if total <= 0:
        window.statusBar().showMessage("PDF has no pages.", 5000); return
    spec, ok = QInputDialog.getText(
        window, "Extract pages",
        f"Page range (1..{total}). Examples: '1-3', '1,3,5', "
        f"'1-3,7,10-end'.",
        text=f"1-{total}",
    )
    if not ok or not spec.strip(): return
    try:
        indices = parse_page_range(spec, total)
    except PdfEditError as e:
        _handle_edit_error(window, e, "Bad page range"); return
    out = _suggest_output(window)
    try:
        n = extract_pages(window._current_path, out, indices)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out, f"Extracted {n} page(s) → {Path(out).name}")


def merge_with_dialog(window) -> None:
    """Append one or more other PDFs to the open one."""
    if not _require_pdf(window): return
    paths, _ = QFileDialog.getOpenFileNames(
        window, "Merge PDFs (after current file)", "",
        "PDF (*.pdf)")
    if not paths: return
    out = _suggest_output(window)
    try:
        n = merge_pdfs([window._current_path, *paths], out)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out,
            f"Merged {len(paths) + 1} PDFs ({n} pages total) → {Path(out).name}")


def insert_blank_after_current(window) -> None:
    if not _require_pdf(window): return
    cur = _current_page(window)
    out = _suggest_output(window)
    try:
        n = insert_blank_page(window._current_path, out, after_index=cur)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out,
            f"Inserted blank after page {cur + 1} ({n} pages) → {Path(out).name}")


def insert_blank_at_start(window) -> None:
    if not _require_pdf(window): return
    out = _suggest_output(window)
    try:
        n = insert_blank_page(window._current_path, out, after_index=-1)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out,
            f"Inserted blank at start ({n} pages) → {Path(out).name}")


def reorder_pages_dialog(window) -> None:
    """Prompt for a new page order. The user types a permutation as
    `extract_pages` would parse it; we just call extract since extract
    preserves order."""
    if not _require_pdf(window): return
    total = _page_count(window)
    if total <= 1:
        window.statusBar().showMessage(
            "Need at least 2 pages to reorder.", 5000); return
    spec, ok = QInputDialog.getText(
        window, "Reorder pages",
        f"New page order (1..{total}, comma-separated). Use this to "
        f"shuffle pages.\nExample for 4 pages: '4,1,3,2'.",
        text=",".join(str(i + 1) for i in range(total)),
    )
    if not ok or not spec.strip(): return
    try:
        # Don't dedupe — but reorder requires every page exactly once.
        indices = parse_page_range(spec, total)
        if sorted(indices) != list(range(total)):
            raise PdfEditError(
                f"Reorder needs every page (1..{total}) exactly once.")
    except PdfEditError as e:
        _handle_edit_error(window, e, "Bad reorder spec"); return
    out = _suggest_output(window)
    try:
        n = extract_pages(window._current_path, out, indices)
    except PdfEditError as e:
        _handle_edit_error(window, e); return
    _finish(window, out, f"Reordered {n} pages → {Path(out).name}")

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
from .pdf_annotations import (
    PdfAnnotationError, page_size, list_annotations,
    add_sticky_note, add_freetext, add_highlight, add_underline,
    add_strikeout, add_rectangle, add_circle, add_ink,
    delete_annotations, clear_annotations,
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


# ----------------------------------------------------------- annotations (v3.5 phase 2a) --

def _prompt_rect(window, default_x: float, default_y: float,
                  default_w: float, default_h: float):
    """Prompt for a rectangle as `x,y,width,height` (PDF points).
    Returns the tuple or `None` if cancelled / malformed."""
    spec, ok = QInputDialog.getText(
        window, "Rectangle (PDF points)",
        "Enter `x,y,width,height` in PDF points "
        "(1 pt = 1/72 inch; bottom-left origin):",
        text=f"{default_x},{default_y},{default_w},{default_h}",
    )
    if not ok or not spec.strip(): return None
    parts = [s.strip() for s in spec.split(",")]
    if len(parts) != 4:
        QMessageBox.warning(window, "Bad rectangle",
                            "Expected four comma-separated numbers.")
        return None
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        QMessageBox.warning(window, "Bad rectangle",
                            "Could not parse numbers in rectangle spec.")
        return None


def _prompt_point(window, default_x: float, default_y: float):
    spec, ok = QInputDialog.getText(
        window, "Point (PDF points)",
        "Enter `x,y` in PDF points (1 pt = 1/72 inch):",
        text=f"{default_x},{default_y}",
    )
    if not ok or not spec.strip(): return None
    parts = [s.strip() for s in spec.split(",")]
    if len(parts) != 2:
        QMessageBox.warning(window, "Bad point",
                            "Expected two comma-separated numbers.")
        return None
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        QMessageBox.warning(window, "Bad point",
                            "Could not parse numbers.")
        return None


def _prompt_color(window, title: str, default: str) -> str | None:
    """Prompt for a `#rrggbb` hex color string."""
    text, ok = QInputDialog.getText(
        window, title, "Hex color (#rrggbb):", text=default)
    if not ok or not text.strip(): return None
    return text.strip()


def _handle_annot_error(window, exc: PdfAnnotationError,
                         title: str = "PDF annotation failed"):
    QMessageBox.warning(window, title, str(exc))


def annotate_sticky_note(window) -> None:
    """**PDF → Annotate → Sticky note…** — prompt for text, place pin
    near the top-left of the current page."""
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        pw, ph = page_size(window._current_path, cur)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    text, ok = QInputDialog.getMultiLineText(
        window, "Sticky note", "Note text:")
    if not ok or not text.strip(): return
    # Default position: top-left corner-ish (PDF origin is bottom-left,
    # so a "top-left" point is at (50, page_height - 50)).
    point = _prompt_point(window, default_x=50, default_y=ph - 50)
    if point is None: return
    out = _suggest_output(window)
    try:
        add_sticky_note(window._current_path, out, cur,
                        point[0], point[1], text)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Added sticky note on page {cur + 1} → {Path(out).name}")


def annotate_freetext(window) -> None:
    """**Free-text box…** on current page."""
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        pw, ph = page_size(window._current_path, cur)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    text, ok = QInputDialog.getMultiLineText(
        window, "Free-text annotation", "Text:")
    if not ok or not text.strip(): return
    rect = _prompt_rect(window, 50, ph - 80, 300, 30)
    if rect is None: return
    color = _prompt_color(window, "Text color", "#000000")
    if color is None: return
    out = _suggest_output(window)
    try:
        add_freetext(window._current_path, out, cur, rect,
                     text, color=color)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Added free-text on page {cur + 1} → {Path(out).name}")


def annotate_highlight(window) -> None:
    """**Highlight rectangle…** on current page."""
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        pw, ph = page_size(window._current_path, cur)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    rect = _prompt_rect(window, 50, ph / 2, 200, 20)
    if rect is None: return
    color = _prompt_color(window, "Highlight color", "#FFFF00")
    if color is None: return
    out = _suggest_output(window)
    try:
        add_highlight(window._current_path, out, cur, rect, color=color)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Highlighted region on page {cur + 1} → {Path(out).name}")


def annotate_rectangle(window) -> None:
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        pw, ph = page_size(window._current_path, cur)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    rect = _prompt_rect(window, 50, ph / 2, 200, 100)
    if rect is None: return
    color = _prompt_color(window, "Stroke color", "#FF0000")
    if color is None: return
    out = _suggest_output(window)
    try:
        add_rectangle(window._current_path, out, cur, rect, color=color)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Added rectangle on page {cur + 1} → {Path(out).name}")


def annotate_circle(window) -> None:
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        pw, ph = page_size(window._current_path, cur)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    rect = _prompt_rect(window, 50, ph / 2, 100, 100)
    if rect is None: return
    color = _prompt_color(window, "Stroke color", "#FF0000")
    if color is None: return
    out = _suggest_output(window)
    try:
        add_circle(window._current_path, out, cur, rect, color=color)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Added circle on page {cur + 1} → {Path(out).name}")


def show_annotations_dialog(window) -> None:
    """**Annotations → List…** — show every annotation in the file."""
    if not _require_pdf(window): return
    try:
        anns = list_annotations(window._current_path)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    if not anns:
        QMessageBox.information(window, "Annotations",
                                 "This PDF has no annotations.")
        return
    lines = [
        f"#{a['index']:>2}  page {a['page'] + 1}  {a['type']:<12}  "
        f"rect=({a['rect'][0]:.0f},{a['rect'][1]:.0f},"
        f"{a['rect'][2]:.0f}×{a['rect'][3]:.0f})"
        + (f"  '{a['content'][:60]}'" if a['content'] else "")
        for a in anns
    ]
    QMessageBox.information(window, f"{len(anns)} annotation(s)",
                             "\n".join(lines))


def delete_annotation_dialog(window) -> None:
    """**Annotations → Delete one…** — prompt for an `index` from the
    list and remove just that annotation."""
    if not _require_pdf(window): return
    try:
        anns = list_annotations(window._current_path)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    if not anns:
        window.statusBar().showMessage(
            "Delete annotation: no annotations to delete.", 4000)
        return
    labels = [f"#{a['index']}  page {a['page'] + 1}  {a['type']}"
              + (f" — {a['content'][:40]}" if a['content'] else "")
              for a in anns]
    chosen, ok = QInputDialog.getItem(
        window, "Delete annotation",
        f"Pick one of {len(anns)} to delete:",
        labels, 0, False)
    if not ok: return
    idx = anns[labels.index(chosen)]["index"]
    out = _suggest_output(window)
    try:
        n = delete_annotations(window._current_path, out, [idx])
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Deleted annotation #{idx} → {Path(out).name}")


def clear_annotations_action(window) -> None:
    """**Annotations → Clear all…** — confirm, then strip every
    annotation."""
    if not _require_pdf(window): return
    try:
        anns = list_annotations(window._current_path)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    if not anns:
        window.statusBar().showMessage(
            "Clear annotations: nothing to clear.", 4000); return
    ret = QMessageBox.question(
        window, "Clear all annotations",
        f"Remove all {len(anns)} annotations?\n"
        f"The original file is left untouched.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if ret != QMessageBox.StandardButton.Yes: return
    out = _suggest_output(window)
    try:
        n = clear_annotations(window._current_path, out)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Cleared {n} annotations → {Path(out).name}")


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

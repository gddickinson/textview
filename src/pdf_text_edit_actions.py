"""Action handlers for inline PDF text editing (v3.5 tier 3).

Three flavours:

1. **Pick a span by list** (`edit_text_dialog`): show every text
   span on the current page in a picker, user types replacement.
2. **Find and replace across the document** (`find_replace_dialog`):
   query + replacement + case-sensitive toggle.
3. **Mouse-driven**: the user enters "edit text" annotation mode on
   the PDF viewer and clicks a span; the click hits-tests against
   `find_span_at` and opens the replacement dialog at that span.

All three converge on `replace_span_object` (which preserves the
original font / size / colour) or `find_and_replace` (which does
not, since there's no single source span per match).

The handlers live in this file rather than `pdf_actions.py` to
respect the 500-line cap.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from .pdf_actions import (
    _require_pdf, _current_page, _suggest_output, _finish,
)
from .pdf_text_edit import (
    PdfTextEditError, list_text_spans, replace_span_object,
    find_and_replace, find_span_at,
)


def _handle_text_edit_error(window, exc: PdfTextEditError,
                              title: str = "Text edit failed"):
    QMessageBox.warning(window, title, str(exc))


# ----------------------------------------------------------- dialog flows --

def edit_text_dialog(window) -> None:
    """**PDF → Edit text → Pick a span on this page…** — list every
    text span on the current page, user picks one and types a
    replacement."""
    if not _require_pdf(window): return
    cur = _current_page(window)
    try:
        spans = list_text_spans(window._current_path)
    except PdfTextEditError as e:
        _handle_text_edit_error(window, e); return

    page_spans = [s for s in spans if s.page == cur]
    if not page_spans:
        QMessageBox.information(
            window, "No editable text",
            "PyMuPDF found no text spans on this page. The page may "
            "be image-only (e.g. scanned), or text may be drawn as "
            "glyph paths rather than as text operators (some "
            "LaTeX-built PDFs do this). Try the **OCR** workflow "
            "for scanned pages.")
        return

    # Build picker labels — show font, size, content. Truncate long
    # text so the dialog stays readable.
    labels = [
        f"#{s.id:>3}  {s.font[:24]:<24}  {s.size:>5.1f}pt  '{s.text[:60]}'"
        for s in page_spans
    ]
    chosen, ok = QInputDialog.getItem(
        window, "Edit text — pick a span",
        f"{len(page_spans)} text span(s) on page {cur + 1}. "
        f"Pick one to replace:",
        labels, 0, False)
    if not ok: return
    target = page_spans[labels.index(chosen)]
    _prompt_and_replace_span(window, target)


def _prompt_and_replace_span(window, target) -> None:
    """Shared replacement flow: prompt for new text + advise about
    auto-fit, then call replace_span_object."""
    new_text, ok = QInputDialog.getMultiLineText(
        window,
        f"Replace text on page {target.page + 1}",
        (f"Original ({target.size:.1f}pt {target.font}):\n"
         f"  {target.text}\n\n"
         f"Replacement text (longer text will auto-shrink to fit; "
         f"the original font + colour are preserved):"),
        target.text,
    )
    if not ok: return
    if not new_text.strip():
        QMessageBox.warning(window, "Empty replacement",
                            "Replacement text can't be empty. "
                            "Use **Annotations: clear all…** to remove "
                            "or **Page operations** if you want to "
                            "delete the whole region.")
        return
    out = _suggest_output(window)
    try:
        replace_span_object(window._current_path, out, target, new_text)
    except PdfTextEditError as e:
        _handle_text_edit_error(window, e); return
    _finish(window, out,
            f"Replaced '{target.text[:30]}' → '{new_text[:30]}' "
            f"on page {target.page + 1} → {Path(out).name}")


def find_replace_dialog(window) -> None:
    """**PDF → Edit text → Find and replace…** — case-insensitive by
    default. Operates across every page."""
    if not _require_pdf(window): return
    query, ok = QInputDialog.getText(
        window, "Find and replace — query",
        "Find what (across every page):")
    if not ok or not query.strip(): return
    new_text, ok = QInputDialog.getText(
        window, "Find and replace — replacement",
        f"Replace '{query}' with:")
    if not ok or not new_text.strip(): return
    out = _suggest_output(window)
    try:
        res = find_and_replace(window._current_path, out, query, new_text)
    except PdfTextEditError as e:
        _handle_text_edit_error(window, e); return
    if res.total == 0:
        QMessageBox.information(
            window, "Find and replace",
            f"No occurrences of '{query}' found.")
        return
    _finish(window, out,
            f"Replaced {res.total} occurrence(s) of '{query[:30]}' "
            f"→ {Path(out).name}")


# ----------------------------------------------------------- mouse-driven (extends phase 2b) --

def enter_edit_text_mode(window) -> None:
    """Arm the PDF viewer for click-to-edit. On the next click on
    the rendered page, hit-test against `list_text_spans`; if the
    click landed on a span, open the replacement dialog. Reuses
    PdfViewer's annotation_committed signal — we register an
    `edit_text` mode."""
    if not _require_pdf(window): return
    d = window.settings_manager.display
    if getattr(d, "pdf_page_mode", "single") != "single":
        window.settings_manager.update("pdf_page_mode", "single")
    window.viewer.pdf_view.set_annotation_mode("edit_text")
    window.viewer.pdf_view.setFocus()


def _on_edit_text_click(window, mode: str, page: int,
                         rect: tuple, _color: str) -> None:
    """Slot for `pdf_view.annotation_committed` when mode is
    `edit_text`. Hit-tests the click against `list_text_spans`; if
    a span sits under the click, opens the replacement dialog at
    that span."""
    if mode != "edit_text": return
    # The committed rect is (x, y, 1, 1) for a click — pick the
    # press point.
    x, y, _, _ = rect
    try:
        span = find_span_at(window._current_path, page, x, y)
    except PdfTextEditError as e:
        window.viewer.pdf_view.set_annotation_mode("off")
        _handle_text_edit_error(window, e); return
    window.viewer.pdf_view.set_annotation_mode("off")
    if span is None:
        QMessageBox.information(
            window, "No span here",
            f"No editable text span at ({x:.0f}, {y:.0f}) on "
            f"page {page + 1}. Click closer to the text glyphs, or "
            f"use **Edit text → Pick a span on this page…** to "
            f"choose from a list.")
        return
    _prompt_and_replace_span(window, span)


def attach_text_edit_signals(window) -> None:
    """Hook the `edit_text` mode to its commit handler. Called
    once during MainWindow init."""
    window.viewer.pdf_view.annotation_committed.connect(
        lambda mode, page, rect, color:
            _on_edit_text_click(window, mode, page, rect, color))

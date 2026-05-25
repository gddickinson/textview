"""Annotation action handlers — dialog-driven (v3.5 phase 2a) and
mouse-driven (v3.5 phase 2b).

Split out from `pdf_actions.py` once that file outgrew its
500-line cap. The page-edit handlers (rotate / delete / extract /
merge / insert blank / reorder) stay in `pdf_actions.py`; this file
hosts everything that touches `pdf_annotations.py`.

Shared helpers (`_require_pdf`, `_current_page`, `_suggest_output`,
`_finish`) are imported back from `pdf_actions` rather than
duplicated.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .pdf_actions import (
    _require_pdf, _current_page, _suggest_output, _finish,
)
from .pdf_annotations import (
    PdfAnnotationError, page_size, list_annotations,
    add_sticky_note, add_freetext, add_highlight, add_underline,
    add_strikeout, add_rectangle, add_circle, add_ink,
    delete_annotations, clear_annotations,
)
from .pdf_editor import derive_output_path


# ----------------------------------------------------------- prompt helpers --

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


# ----------------------------------------------------------- dialog-driven --

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
        add_freetext(window._current_path, out, cur, rect, text, color=color)
    except PdfAnnotationError as e:
        _handle_annot_error(window, e); return
    _finish(window, out, f"Added free-text on page {cur + 1} → {Path(out).name}")


def annotate_highlight(window) -> None:
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


# ----------------------------------------------------------- mouse-driven (phase 2b) --

def attach_annotation_signals(window) -> None:
    """Wire `PdfViewer.annotation_committed` and
    `annotation_mode_changed` to the bridge handlers below. Call
    once during MainWindow setup."""
    pdf_view = window.viewer.pdf_view
    pdf_view.annotation_committed.connect(
        lambda mode, page, rect, color:
            _on_annotation_committed(window, mode, page, rect, color))
    pdf_view.annotation_mode_changed.connect(
        lambda mode: _on_mode_changed(window, mode))


def enter_annotation_mode(window, mode: str, *,
                          color: str | None = None) -> None:
    """Arm the PDF viewer to capture a click / drag for the given
    annotation type. Auto-switches to single-page render mode (the
    coord conversion assumes single-page layout). Esc cancels."""
    if not _require_pdf(window): return
    d = window.settings_manager.display
    if getattr(d, "pdf_page_mode", "single") != "single":
        window.settings_manager.update("pdf_page_mode", "single")
    if color is None:
        color = {
            "highlight": "#FFFF00", "underline": "#000000",
            "strikeout": "#FF0000", "rect": "#FF0000",
            "circle": "#FF0000", "freetext": "#000000",
            "sticky": "#FFFF00",
        }.get(mode, "#FFFF00")
    window.viewer.pdf_view.set_annotation_mode(mode, color)
    window.viewer.pdf_view.setFocus()


def _on_mode_changed(window, mode: str) -> None:
    sb = window.statusBar()
    if mode == "off":
        sb.clearMessage()
    elif ":" in mode:
        sb.showMessage(mode, 5000)
    else:
        sb.showMessage(
            f"Annotation mode: {mode} — "
            f"{'click' if mode == 'sticky' else 'drag'} on the page, "
            f"Esc to cancel.", 0)


def _on_annotation_committed(window, mode: str, page: int,
                              rect_pdf: tuple, color: str) -> None:
    if not window._current_path: return
    out = derive_output_path(window._current_path)
    x, y, w, h = rect_pdf
    pv = window.viewer.pdf_view
    try:
        if mode == "sticky":
            text, ok = QInputDialog.getMultiLineText(
                window, "Sticky note", "Note text:")
            if not ok or not text.strip():
                pv.set_annotation_mode("off"); return
            add_sticky_note(window._current_path, out, page, x, y, text)
        elif mode == "freetext":
            text, ok = QInputDialog.getMultiLineText(
                window, "Free-text annotation", "Text:")
            if not ok or not text.strip():
                pv.set_annotation_mode("off"); return
            add_freetext(window._current_path, out, page,
                         (x, y, w, h), text, color=color)
        elif mode == "highlight":
            add_highlight(window._current_path, out, page,
                          (x, y, w, h), color=color)
        elif mode == "underline":
            add_underline(window._current_path, out, page,
                          (x, y, w, h), color=color)
        elif mode == "strikeout":
            add_strikeout(window._current_path, out, page,
                          (x, y, w, h), color=color)
        elif mode == "rect":
            add_rectangle(window._current_path, out, page,
                          (x, y, w, h), color=color)
        elif mode == "circle":
            add_circle(window._current_path, out, page,
                       (x, y, w, h), color=color)
        else:
            return
    except PdfAnnotationError as e:
        pv.set_annotation_mode("off")
        _handle_annot_error(window, e); return
    pv.set_annotation_mode("off")
    window.statusBar().showMessage(
        f"Added {mode} on page {page + 1} → {Path(out).name}", 5000)
    window.open_file(out, confirm=False)

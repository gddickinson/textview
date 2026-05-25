"""PDF annotations via PyMuPDF (`fitz`).

Phase 2a of v3.5 PDF editing: library + dialog-driven menu actions
for the standard annotation types. Phase 2b (mouse-driven overlay
UX) reuses this same backend.

All operations mirror `pdf_editor.py`'s shape: take an input path, an
output path, and parameters; **never** mutate the input file. The
output file is opened in a new tab by the `pdf_actions.py` bridge.

PyMuPDF is lazy-imported with a friendly install hint so a missing
optional dep raises `PdfAnnotationError` rather than crashing.

Coordinate system: PDF points (1 pt = 1/72 inch), origin at the
**bottom-left** of the page (PDF convention). Page width/height are
exposed via `page_size(path, page_index)` so a UI can convert from
its own coordinate system.

Supported annotation types:
  - **Sticky note** (`Text` annotation) — icon at a single point with
    a popup message.
  - **Free-text** — text written directly onto the page in a box.
  - **Highlight** / **underline** / **strikeout** — over a rectangle.
  - **Rectangle** / **circle** / **line** — geometric shapes.
  - **Ink** (freehand) — one or more lists of points forming strokes.

Not built:
  - Stamp annotations (need icon assets).
  - Sound / movie / 3D annotations.
  - True text-aware highlighting (would need PDF text extraction to
    snap a rectangle to glyph boundaries — separate effort).
  - Redaction is a special case that requires content removal; ship
    as a follow-up.
"""
from __future__ import annotations

from pathlib import Path


class PdfAnnotationError(Exception):
    """Wraps every failure (missing dep, bad page index, malformed
    coords) so callers don't need to import fitz to handle errors."""


# ----------------------------------------------------------- internals --

def _fitz():
    """Lazy import for PyMuPDF with a friendly error."""
    try:
        import fitz  # type: ignore
    except ImportError as e:
        raise PdfAnnotationError(
            "PDF annotations need PyMuPDF. "
            "Install with `pip install PyMuPDF`."
        ) from e
    return fitz


def _open(input_path: str):
    fitz = _fitz()
    try:
        return fitz.open(input_path)
    except Exception as e:
        raise PdfAnnotationError(f"Could not open PDF: {e}") from e


def _validate_page(doc, page_index: int):
    if not 0 <= page_index < doc.page_count:
        raise PdfAnnotationError(
            f"Page index {page_index} out of range (0..{doc.page_count - 1}).")
    return doc[page_index]


def _save(doc, output_path: str) -> None:
    """Save the in-memory doc to a NEW path. Always uses
    `garbage=4, deflate=True` to compact the output."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=4, deflate=True)
    except Exception as e:
        raise PdfAnnotationError(f"Could not save PDF: {e}") from e
    finally:
        try: doc.close()
        except Exception: pass


def _parse_hex_color(spec: str) -> tuple[float, float, float]:
    """`#rrggbb` or `#rgb` → (r, g, b) floats in 0..1. PyMuPDF expects
    floats, not bytes."""
    s = (spec or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise PdfAnnotationError(f"Bad hex color {spec!r}; expected '#rrggbb'.")
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError as e:
        raise PdfAnnotationError(f"Bad hex color {spec!r}: {e}") from e
    return r, g, b


def _validate_rect(rect) -> tuple[float, float, float, float]:
    """Coerce a (x, y, w, h) tuple of numbers into floats. Width and
    height must be positive."""
    try:
        x, y, w, h = (float(v) for v in rect)
    except (TypeError, ValueError) as e:
        raise PdfAnnotationError(
            "rect must be a (x, y, width, height) tuple of numbers"
        ) from e
    if w <= 0 or h <= 0:
        raise PdfAnnotationError(
            f"Width and height must be positive (got {w}×{h}).")
    return x, y, w, h


# ----------------------------------------------------------- introspection --

def page_size(input_path: str, page_index: int) -> tuple[float, float]:
    """Return `(width_pt, height_pt)` of the chosen page. Useful for
    a UI mapping its own coord system to PDF points."""
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        rect = page.rect
        return float(rect.width), float(rect.height)
    finally:
        try: doc.close()
        except Exception: pass


def list_annotations(input_path: str) -> list[dict]:
    """Walk every page, return a flat list of dicts with keys:
    `index` (sequential id used by `delete_annotations`), `page`,
    `type` (PyMuPDF annot type name), `rect` (x, y, w, h tuple in PDF
    points), `content` (popup text). Empty list if no annotations
    anywhere."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        out: list[dict] = []
        idx = 0
        for p in range(doc.page_count):
            page = doc[p]
            annot = page.first_annot
            while annot is not None:
                r = annot.rect
                out.append({
                    "index": idx,
                    "page": p,
                    "type": annot.type[1] if annot.type else "Unknown",
                    "rect": (float(r.x0), float(r.y0),
                             float(r.width), float(r.height)),
                    "content": annot.info.get("content", "") if annot.info else "",
                })
                idx += 1
                annot = annot.next
        return out
    finally:
        try: doc.close()
        except Exception: pass


# ----------------------------------------------------------- add ops --

def add_sticky_note(input_path: str, output_path: str,
                     page_index: int, x: float, y: float,
                     text: str, *, author: str = "TextView") -> None:
    """Place a sticky-note pin at `(x, y)` on the given page; popup
    holds `text`."""
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        annot = page.add_text_annot((float(x), float(y)), text)
        annot.set_info(title=author, content=text)
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_sticky_note failed: {e}") from e
    _save(doc, output_path)


def add_freetext(input_path: str, output_path: str,
                  page_index: int, rect: tuple,
                  text: str, *, font_size: float = 12.0,
                  color: str = "#000000",
                  fill: str | None = None) -> None:
    """Add a free-text annotation: text rendered directly on the page
    inside `rect=(x, y, w, h)` in PDF points."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        fr, fg, fb = _parse_hex_color(color)
        kwargs = dict(text=text, fontsize=float(font_size),
                      text_color=(fr, fg, fb))
        if fill:
            kwargs["fill_color"] = _parse_hex_color(fill)
        annot = page.add_freetext_annot(fitz.Rect(x, y, x + w, y + h), **kwargs)
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_freetext failed: {e}") from e
    _save(doc, output_path)


def add_highlight(input_path: str, output_path: str,
                   page_index: int, rect: tuple,
                   *, color: str = "#FFFF00") -> None:
    """Highlight a rectangular region. The whole rect gets a coloured
    overlay — there's no glyph-aware snapping (that's a separate
    effort with PDF text extraction)."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        cr, cg, cb = _parse_hex_color(color)
        annot = page.add_highlight_annot(fitz.Rect(x, y, x + w, y + h))
        annot.set_colors(stroke=(cr, cg, cb))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_highlight failed: {e}") from e
    _save(doc, output_path)


def add_underline(input_path: str, output_path: str,
                   page_index: int, rect: tuple,
                   *, color: str = "#000000") -> None:
    """Underline a region (text-style decoration without text snapping)."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        cr, cg, cb = _parse_hex_color(color)
        annot = page.add_underline_annot(fitz.Rect(x, y, x + w, y + h))
        annot.set_colors(stroke=(cr, cg, cb))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_underline failed: {e}") from e
    _save(doc, output_path)


def add_strikeout(input_path: str, output_path: str,
                   page_index: int, rect: tuple,
                   *, color: str = "#FF0000") -> None:
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        cr, cg, cb = _parse_hex_color(color)
        annot = page.add_strikeout_annot(fitz.Rect(x, y, x + w, y + h))
        annot.set_colors(stroke=(cr, cg, cb))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_strikeout failed: {e}") from e
    _save(doc, output_path)


def add_rectangle(input_path: str, output_path: str,
                   page_index: int, rect: tuple,
                   *, color: str = "#FF0000",
                   fill: str | None = None,
                   width: float = 1.0) -> None:
    """Draw a rectangle outline (or filled if `fill` is given)."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        cr, cg, cb = _parse_hex_color(color)
        annot = page.add_rect_annot(fitz.Rect(x, y, x + w, y + h))
        annot.set_border(width=float(width))
        if fill is not None:
            fr, fg, fb = _parse_hex_color(fill)
            annot.set_colors(stroke=(cr, cg, cb), fill=(fr, fg, fb))
        else:
            annot.set_colors(stroke=(cr, cg, cb))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_rectangle failed: {e}") from e
    _save(doc, output_path)


def add_circle(input_path: str, output_path: str,
                page_index: int, rect: tuple,
                *, color: str = "#FF0000",
                fill: str | None = None,
                width: float = 1.0) -> None:
    """Draw an ellipse / circle within `rect`. Mirrors `add_rectangle`."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        x, y, w, h = _validate_rect(rect)
        cr, cg, cb = _parse_hex_color(color)
        annot = page.add_circle_annot(fitz.Rect(x, y, x + w, y + h))
        annot.set_border(width=float(width))
        if fill is not None:
            fr, fg, fb = _parse_hex_color(fill)
            annot.set_colors(stroke=(cr, cg, cb), fill=(fr, fg, fb))
        else:
            annot.set_colors(stroke=(cr, cg, cb))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_circle failed: {e}") from e
    _save(doc, output_path)


def add_ink(input_path: str, output_path: str,
             page_index: int, strokes: list[list[tuple]],
             *, color: str = "#000000",
             width: float = 1.5) -> None:
    """Add a freehand "ink" annotation. `strokes` is a list of
    strokes; each stroke is a list of `(x, y)` points. Lifting the
    pen between strokes is what creates multiple entries."""
    fitz = _fitz()
    if not strokes or not any(strokes):
        raise PdfAnnotationError("`strokes` must contain at least one non-empty stroke.")
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        cr, cg, cb = _parse_hex_color(color)
        # PyMuPDF wants raw seq-of-seq-of-float-pairs, not `fitz.Point`s.
        py_strokes = [[(float(x), float(y)) for (x, y) in stroke]
                       for stroke in strokes if stroke]
        annot = page.add_ink_annot(py_strokes)
        annot.set_colors(stroke=(cr, cg, cb))
        annot.set_border(width=float(width))
        annot.update()
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"add_ink failed: {e}") from e
    _save(doc, output_path)


# ----------------------------------------------------------- delete ops --

def delete_annotations(input_path: str, output_path: str,
                        indices: list[int]) -> int:
    """Remove the annotations whose `index` (as returned by
    `list_annotations`) appears in `indices`. Returns the count of
    annotations removed."""
    fitz = _fitz()
    drop = set(int(i) for i in indices)
    if not drop:
        raise PdfAnnotationError("No annotation indices supplied.")
    doc = _open(input_path)
    try:
        seen = 0
        removed = 0
        for p in range(doc.page_count):
            page = doc[p]
            # Collect first, then delete — modifying during traversal
            # of the linked-list confuses .next().
            annots = []
            a = page.first_annot
            while a is not None:
                annots.append(a)
                a = a.next
            for a in annots:
                if seen in drop:
                    page.delete_annot(a)
                    removed += 1
                seen += 1
        if removed != len(drop):
            # Some indices didn't match an annotation — still produce
            # the output but warn the caller.
            pass
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"delete_annotations failed: {e}") from e
    _save(doc, output_path)
    return removed


def clear_annotations(input_path: str, output_path: str,
                       page_index: int | None = None) -> int:
    """Remove every annotation from the doc, or from one page when
    `page_index` is given. Returns the count removed."""
    fitz = _fitz()
    doc = _open(input_path)
    try:
        removed = 0
        pages = ([page_index] if page_index is not None
                 else range(doc.page_count))
        for p in pages:
            if not 0 <= p < doc.page_count:
                raise PdfAnnotationError(
                    f"Page index {p} out of range.")
            page = doc[p]
            annots = []
            a = page.first_annot
            while a is not None:
                annots.append(a)
                a = a.next
            for a in annots:
                page.delete_annot(a)
                removed += 1
    except PdfAnnotationError:
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfAnnotationError(f"clear_annotations failed: {e}") from e
    _save(doc, output_path)
    return removed

"""Inline PDF text editing via PyMuPDF redaction-with-replacement.

This is v3.5 tier 3 — the **honest** version of "Adobe-style PDF
editing". It works for the common cases (typo fixes, label changes,
form-like single-phrase edits) and is explicit about what it can't
do.

The primitive PyMuPDF gives us:

    page.add_redact_annot(rect, text="new", fontname="helv",
                          fontsize=12, text_color=(r,g,b),
                          fill=(r,g,b))
    page.apply_redactions()

This removes whatever was in `rect` and writes `text` in its place
using `fontname` at `fontsize`. The result is a *real* edited PDF
(not just an annotation overlay).

## What works

- **Single-span replacement**: identify a text span via
  `list_text_spans(...)`, replace its content.
- **Find-and-replace across the doc**: search for a string, replace
  every match.
- **Font preservation** for the PDF base 14 fonts (Helvetica, Times,
  Courier and their variants). The font name extracted by
  `get_text("dict")` is exactly the string `add_redact_annot` wants.

## What doesn't work — and why we don't pretend it does

- **Long replacements**: PyMuPDF auto-shrinks `fontsize` to make the
  string fit the original bbox. Useful default, but surprising —
  our `replace_span` lets the caller override `fontsize` to disable
  the shrink and accept clipping instead.
- **Cross-line edits**: a "span" is one line of text in PDF land.
  Replacements that span line breaks aren't supported — the caller
  would have to merge spans first, which loses the original layout.
- **Reflowing surrounding text**: PDFs don't model paragraphs.
  Removing or adding characters never shifts the rest of the line,
  let alone the next line. Use cases where reflow matters → wrong
  tool.
- **Unicode characters not in the original font**: render as `?`
  with the base 14 fonts. The caller can pass a different
  `fontname` (e.g. `helv` for full Latin coverage) and accept a
  visible font-substitution.
- **PDFs where text is drawn as glyph paths**: some LaTeX builds,
  scanned PDFs, certain InDesign output. `list_text_spans` returns
  an empty list — there's nothing for us to edit.

`PdfTextEditError` wraps every failure mode so callers don't need
to handle PyMuPDF exceptions directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class PdfTextEditError(Exception):
    """Wraps every text-editing failure (missing PyMuPDF, bad page
    index, bad bbox, IO error)."""


# ----------------------------------------------------------- internals --

def _fitz():
    try:
        import fitz  # type: ignore
    except ImportError as e:
        raise PdfTextEditError(
            "Inline text editing needs PyMuPDF. "
            "Install with `pip install PyMuPDF`."
        ) from e
    return fitz


def _open(input_path: str):
    fitz = _fitz()
    try:
        return fitz.open(input_path)
    except Exception as e:
        raise PdfTextEditError(f"Could not open PDF: {e}") from e


def _validate_page(doc, page_index: int):
    if not 0 <= page_index < doc.page_count:
        raise PdfTextEditError(
            f"Page index {page_index} out of range (0..{doc.page_count - 1}).")
    return doc[page_index]


def _save(doc, output_path: str) -> None:
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=4, deflate=True)
    except Exception as e:
        raise PdfTextEditError(f"Could not save PDF: {e}") from e
    finally:
        try: doc.close()
        except Exception: pass


def _int_color_to_floats(c: int) -> tuple[float, float, float]:
    """PyMuPDF returns colors as packed ints (0xRRGGBB). Convert to
    the (r, g, b) 0..1 float tuples it wants on the write side."""
    r = ((c >> 16) & 0xFF) / 255.0
    g = ((c >> 8) & 0xFF) / 255.0
    b = (c & 0xFF) / 255.0
    return r, g, b


def _parse_hex_color(spec: str) -> tuple[float, float, float]:
    """`#rrggbb` / `#rgb` / no-hash → 0..1 floats. Same shape as
    `pdf_annotations._parse_hex_color` but kept local so this module
    stands alone."""
    s = (spec or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise PdfTextEditError(f"Bad hex color {spec!r}; expected '#rrggbb'.")
    return (int(s[0:2], 16) / 255.0,
            int(s[2:4], 16) / 255.0,
            int(s[4:6], 16) / 255.0)


# ----------------------------------------------------------- span listing --

@dataclass
class TextSpan:
    """A single editable text span on a PDF page. The `id` is
    sequential per-document (page-walk order) so dialog pickers can
    refer back to it; `(x0, y0, x1, y1)` is in PDF points with
    top-left origin (MuPDF convention)."""
    id: int
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    font: str
    size: float
    color: int           # packed 0xRRGGBB int — convert via `_int_color_to_floats`

    def color_hex(self) -> str:
        """Return the span's colour as `#rrggbb`."""
        return f"#{self.color & 0xFFFFFF:06X}"


def list_text_spans(input_path: str) -> list[TextSpan]:
    """Return every editable text span across every page.

    A span is the unit PyMuPDF identifies as "this run of text shares
    one font, size, and colour on one line." That's the natural
    granularity for inline editing — anything smaller (per-character)
    loses font metadata, anything larger (per-paragraph) doesn't
    exist in the PDF.
    """
    doc = _open(input_path)
    try:
        out: list[TextSpan] = []
        seq = 0
        for p in range(doc.page_count):
            page = doc[p]
            tdict = page.get_text("dict")
            for block in tdict.get("blocks", []):
                if block.get("type") != 0:   # 0 = text block; 1 = image
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span.get("bbox") or (0, 0, 0, 0)
                        if not span.get("text", "").strip():
                            continue        # skip whitespace-only spans
                        out.append(TextSpan(
                            id=seq, page=p,
                            bbox=tuple(float(v) for v in bbox),
                            text=span.get("text", ""),
                            font=span.get("font", "Helvetica"),
                            size=float(span.get("size", 12)),
                            color=int(span.get("color", 0)),
                        ))
                        seq += 1
        return out
    finally:
        try: doc.close()
        except Exception: pass


def find_span_at(input_path: str, page_index: int,
                  x: float, y: float) -> TextSpan | None:
    """Hit-test: return the span whose bbox contains `(x, y)` (PDF
    points, top-left origin) on the given page. Used by the
    click-to-edit mouse mode."""
    for s in list_text_spans(input_path):
        if s.page != page_index:
            continue
        x0, y0, x1, y1 = s.bbox
        if x0 <= x <= x1 and y0 <= y <= y1:
            return s
    return None


# ----------------------------------------------------------- replacement --

def replace_span(input_path: str, output_path: str,
                  page_index: int,
                  bbox: tuple[float, float, float, float],
                  new_text: str,
                  *,
                  fontname: str = "helv",
                  fontsize: float | None = None,
                  text_color: str = "#000000",
                  fill: str = "#FFFFFF",
                  align: int = 0) -> None:
    """Replace whatever PDF content sits inside `bbox` on
    `page_index` with `new_text`. The original text is removed
    (via PyMuPDF's redaction primitive); the replacement is drawn
    in its place.

    `fontsize=None` lets PyMuPDF auto-fit the string to the bbox.
    Pass an explicit size to keep the original visual size — but
    longer text will then be clipped.

    `fill` is the background colour used for the area where the
    old text was. White is the right default for most pages; if
    the document has a tinted page bg, the caller must override.

    `align` is 0=left, 1=center, 2=right.
    """
    fitz = _fitz()
    if not new_text:
        raise PdfTextEditError("Replacement text is empty.")
    if any(v != v for v in bbox) or any(  # NaN check
            v is None for v in bbox):
        raise PdfTextEditError(f"Bad bbox: {bbox!r}")
    doc = _open(input_path)
    try:
        page = _validate_page(doc, page_index)
        rect = fitz.Rect(*bbox)
        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
            raise PdfTextEditError(f"Empty / inverted bbox: {bbox!r}")
        tc = _parse_hex_color(text_color)
        fc = _parse_hex_color(fill)
        # `fontsize=None` is what PyMuPDF accepts to mean auto-fit.
        kwargs = dict(
            text=new_text, fontname=fontname,
            text_color=tc, fill=fc, align=int(align),
            cross_out=False,
        )
        if fontsize is not None:
            kwargs["fontsize"] = float(fontsize)
        page.add_redact_annot(rect, **kwargs)
        page.apply_redactions()
    except PdfTextEditError:
        try: doc.close()
        except Exception: pass
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfTextEditError(f"Replace failed: {e}") from e
    _save(doc, output_path)


# ----------------------------------------------------------- find/replace --

@dataclass
class FindReplaceResult:
    """Returned from `find_and_replace`. `replacements_per_page` is
    a list[int] indexed by page; `total` is the sum."""
    total: int
    replacements_per_page: list[int]


def find_and_replace(input_path: str, output_path: str,
                      query: str, new_text: str,
                      *,
                      case_sensitive: bool = False,
                      fontname: str = "helv",
                      fontsize: float | None = None,
                      text_color: str = "#000000",
                      fill: str = "#FFFFFF") -> FindReplaceResult:
    """Find every occurrence of `query` in the document and replace
    it with `new_text`. Returns a count.

    Caveat (documented loudly): `add_redact_annot` operates on the
    bbox of each match — it does **not** reflow surrounding text.
    If your replacement is longer than the original the new text
    shrinks; if shorter you get visible empty space where the old
    text was.
    """
    fitz = _fitz()
    if not query:
        raise PdfTextEditError("Empty query.")
    if not new_text:
        raise PdfTextEditError("Empty replacement text.")
    doc = _open(input_path)
    try:
        tc = _parse_hex_color(text_color)
        fc = _parse_hex_color(fill)
        per_page: list[int] = []
        flags = 0 if case_sensitive else fitz.TEXT_INHIBIT_SPACES
        for p in range(doc.page_count):
            page = doc[p]
            # PyMuPDF's search_for is case-insensitive by default;
            # the `quads` argument gives finer rects but for our
            # purposes the default bbox results are correct.
            try:
                hits = page.search_for(query)
            except Exception:
                hits = []
            page_count = 0
            for r in hits:
                kw = dict(
                    text=new_text, fontname=fontname,
                    text_color=tc, fill=fc, cross_out=False,
                )
                if fontsize is not None:
                    kw["fontsize"] = float(fontsize)
                page.add_redact_annot(r, **kw)
                page_count += 1
            if page_count:
                page.apply_redactions()
            per_page.append(page_count)
    except PdfTextEditError:
        try: doc.close()
        except Exception: pass
        raise
    except Exception as e:
        try: doc.close()
        except Exception: pass
        raise PdfTextEditError(f"find_and_replace failed: {e}") from e
    _save(doc, output_path)
    return FindReplaceResult(
        total=sum(per_page), replacements_per_page=per_page)


# ----------------------------------------------------------- convenience --

def replace_span_object(input_path: str, output_path: str,
                         span: TextSpan, new_text: str,
                         *,
                         keep_size: bool = True,
                         keep_color: bool = True,
                         keep_font: bool = True,
                         fill: str = "#FFFFFF",
                         fontsize_override: float | None = None,
                         font_override: str | None = None,
                         color_override: str | None = None) -> None:
    """Bridge between `list_text_spans` and `replace_span`. Takes a
    `TextSpan` dataclass and copies its font/size/colour by default,
    letting the caller selectively override."""
    font = (font_override if font_override is not None
            else (span.font if keep_font else "helv"))
    size = (fontsize_override if fontsize_override is not None
            else (span.size if keep_size else None))
    color = (color_override if color_override is not None
             else (span.color_hex() if keep_color else "#000000"))
    replace_span(
        input_path, output_path, span.page, span.bbox, new_text,
        fontname=font, fontsize=size, text_color=color, fill=fill,
    )

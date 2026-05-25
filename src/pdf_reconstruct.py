"""Reconstruct an editable copy of a PDF in another format.

The "edit via copy" alternative to inline PDF editing (`pdf_text_edit`):
convert PDF → Markdown or DOCX, let the user edit that, then
re-export to PDF through the existing pipelines.

Two routes, both lazy-imported:

1. **PDF → Markdown** via `pymupdf4llm.to_markdown(path)`.
   `pymupdf4llm` is the Artifex helper that builds on PyMuPDF
   (already a dep) and produces clean Markdown — headings,
   pipe-tables, lists, code fences, image refs. Loses absolute
   positioning, font choices, and decorative formatting; the
   trade-off is that Markdown is **the** editable form. Round-trip
   path: edit the markdown in TextView → save → use the existing
   **Save As → .pdf** or `latex → pdf` flow to re-export.

2. **PDF → DOCX** via `pdf2docx.Converter`. Preserves layout
   reasonably well for business documents — paragraphs, tables,
   images, basic font styling. Struggles with multi-column,
   footnotes, math, rotated text. Round-trip path: edit the DOCX
   in Word/LibreOffice → reload in TextView.

What's deliberately NOT here:
- **PDF → LaTeX**: no honest open-source tool exists. Even
  LaTeX-generated PDFs can't be reverse-engineered to source.
- **PDF → HTML via pdf2htmlEX**: C++ build hell.
- **ML-based reconstruction** (marker, Mathpix-style): heavy
  dependency, separate effort.

`PdfReconstructError` wraps every failure (missing dep, parse
error, corrupt PDF) so callers don't need to handle library-
specific exceptions.
"""
from __future__ import annotations

from pathlib import Path


class PdfReconstructError(Exception):
    """Wraps every reconstruction failure mode."""


# ----------------------------------------------------------- internals --

def _suggest_sibling(input_path: str, suffix: str, new_ext: str) -> str:
    """Return `<stem>-<suffix>.<new_ext>` next to `input_path`, with
    auto-dedupe (`-2`, `-3`, …) if a file at that name already
    exists. Mirrors `pdf_editor.derive_output_path`'s shape."""
    src = Path(input_path)
    base = src.with_name(f"{src.stem}-{suffix}.{new_ext.lstrip('.')}")
    if not base.exists():
        return str(base)
    i = 2
    while True:
        cand = src.with_name(f"{src.stem}-{suffix}-{i}.{new_ext.lstrip('.')}")
        if not cand.exists():
            return str(cand)
        i += 1


# ----------------------------------------------------------- PDF → Markdown --

def pdf_to_markdown(input_path: str, output_path: str | None = None,
                     *, pages: list[int] | None = None) -> str:
    """Convert `input_path` to Markdown and write to `output_path`.

    If `output_path` is None, write to a sibling `<stem>-converted.md`.
    `pages` (0-based) limits the conversion to a subset.

    Returns the on-disk output path.
    """
    src = Path(input_path)
    if not src.is_file():
        raise PdfReconstructError(f"Source PDF not found: {input_path}")
    try:
        import pymupdf4llm  # type: ignore
    except ImportError as e:
        raise PdfReconstructError(
            "PDF → Markdown needs pymupdf4llm. "
            "Install with `pip install pymupdf4llm`. "
            "(AGPL-licensed; same as PyMuPDF.)"
        ) from e
    try:
        kwargs = {}
        if pages is not None:
            kwargs["pages"] = list(pages)
        md_text = pymupdf4llm.to_markdown(str(src), **kwargs)
    except Exception as e:
        raise PdfReconstructError(f"PDF → Markdown failed: {e}") from e

    out = output_path or _suggest_sibling(input_path, "converted", "md")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    try:
        Path(out).write_text(md_text, encoding="utf-8")
    except OSError as e:
        raise PdfReconstructError(f"Could not write Markdown: {e}") from e
    return out


# ----------------------------------------------------------- PDF → DOCX --

def pdf_to_docx(input_path: str, output_path: str | None = None,
                 *, pages: list[int] | None = None) -> str:
    """Convert `input_path` to DOCX and write to `output_path`.

    If `output_path` is None, write to a sibling
    `<stem>-converted.docx`. `pages` (0-based) limits the
    conversion to a subset.

    Returns the on-disk output path.

    Quality caveats: layout preservation is good for plain text +
    simple tables + images; **struggles with** multi-column,
    footnotes, math equations, rotated text. The Artifex
    maintainers now point users at MuPDF.NET for higher-fidelity
    conversion, but pdf2docx is still the realistic pure-Python
    option.
    """
    src = Path(input_path)
    if not src.is_file():
        raise PdfReconstructError(f"Source PDF not found: {input_path}")
    try:
        from pdf2docx import Converter  # type: ignore
    except ImportError as e:
        raise PdfReconstructError(
            "PDF → DOCX needs pdf2docx. "
            "Install with `pip install pdf2docx`."
        ) from e

    out = output_path or _suggest_sibling(input_path, "converted", "docx")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv = None
    try:
        cv = Converter(str(src))
        kwargs: dict = {}
        if pages is not None:
            kwargs["pages"] = list(pages)
        cv.convert(out, **kwargs)
    except Exception as e:
        # Clean up the half-written file so the user doesn't end up
        # with a corrupt sibling.
        try: Path(out).unlink(missing_ok=True)
        except Exception: pass
        raise PdfReconstructError(f"PDF → DOCX failed: {e}") from e
    finally:
        if cv is not None:
            try: cv.close()
            except Exception: pass
    return out

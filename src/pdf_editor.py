"""Page-level PDF editing — rotate, delete, extract, reorder, merge,
insert blank.

`pypdf` is already a TextView dependency (the document-extraction
path uses it for text). This module just adds the write-side
operations, all of which are well-supported and stable in pypdf 6.x.

Out of scope (intentional):
- **Inline text editing** of an existing PDF. The PDF format positions
  glyphs individually; editing "the word in paragraph 3" means
  identifying and re-typesetting a text block, which neither pypdf nor
  any other Python library does reliably. Adobe Acrobat itself can
  garble layouts on this operation.
- **Annotations** (highlight / sticky note / freehand). Would need
  `PyMuPDF` plus substantial UI work to position the user's cursor
  inside a PDF page coordinate system. Tracked as a follow-up.
- **Cryptographic signing**. Needs `endesive` + OpenSSL workflow.

Every operation here writes to a **new** path. The caller (typically
`MainWindow.pdf_edit_*` action handlers) chooses whether that's a
sibling `*-edited.pdf` or an explicit Save-As destination. The input
file is never mutated.
"""
from __future__ import annotations

import re
from pathlib import Path


class PdfEditError(Exception):
    """Raised when a PDF page operation fails (corrupt file, bad page
    index, encrypted-without-password, etc.). Always wraps the
    underlying pypdf exception so the caller doesn't need to import
    pypdf to handle errors."""


# ---------------------------------------------------------- helpers --

def _open_reader(input_path: str):
    """Open `input_path` with pypdf. Raises `PdfEditError` for any
    failure mode the user could trip — bad path, corrupt file,
    encrypted without password."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as e:
        raise PdfEditError("pypdf is required for PDF editing") from e
    try:
        reader = PdfReader(input_path)
    except Exception as e:
        raise PdfEditError(f"Could not open PDF: {e}") from e
    if reader.is_encrypted:
        # Try empty password (common for "encrypted-but-readable"
        # PDFs); fall through if that also fails.
        try:
            ok = reader.decrypt("")
            if not ok:
                raise PdfEditError(
                    "PDF is encrypted and requires a password. "
                    "Decrypt it before editing.")
        except Exception as e:
            raise PdfEditError(f"Encrypted PDF: {e}") from e
    return reader


def _new_writer():
    from pypdf import PdfWriter  # type: ignore
    return PdfWriter()


def _validate_indices(indices, page_count: int) -> list[int]:
    """Sort + dedupe + range-check page indices. Returns a sorted
    list. Raises `PdfEditError` on any out-of-range entry."""
    out = sorted(set(int(i) for i in indices))
    for i in out:
        if not 0 <= i < page_count:
            raise PdfEditError(
                f"Page index {i} out of range (0..{page_count - 1}).")
    return out


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """Parse a human page-range string into a list of 0-based indices.

    Accepts comma-separated entries; each entry is either a 1-based
    page number, an inclusive range `a-b`, or the literal `end`.
    Examples (with a 12-page document):

        "1"            → [0]
        "1,3,5"        → [0, 2, 4]
        "1-5"          → [0, 1, 2, 3, 4]
        "1-3,7,10-end" → [0, 1, 2, 6, 9, 10, 11]
        "end"          → [11]

    Raises `PdfEditError` on malformed input or out-of-range page
    numbers. Duplicate pages are preserved in input order (so the
    caller can express "page 3, then page 1, then page 3 again" if
    they want to use this with `reorder_pages`).
    """
    if not spec or not spec.strip():
        raise PdfEditError("Empty page range.")
    out: list[int] = []
    seen: set[int] = set()
    for raw in spec.split(","):
        token = raw.strip().lower()
        if not token: continue
        if "-" in token:
            lo_s, hi_s = token.split("-", 1)
            lo = _parse_page_token(lo_s, page_count)
            hi = _parse_page_token(hi_s, page_count)
            if lo > hi:
                raise PdfEditError(f"Reversed range: {token}")
            for i in range(lo, hi + 1):
                if i not in seen:
                    seen.add(i)
                    out.append(i)
        else:
            i = _parse_page_token(token, page_count)
            if i not in seen:
                seen.add(i)
                out.append(i)
    if not out:
        raise PdfEditError("Page range produced no pages.")
    return out


def _parse_page_token(token: str, page_count: int) -> int:
    token = token.strip().lower()
    if token == "end":
        return page_count - 1
    if not re.fullmatch(r"\d+", token):
        raise PdfEditError(f"Bad page token: {token!r}")
    n = int(token) - 1   # 1-based → 0-based
    if not 0 <= n < page_count:
        raise PdfEditError(
            f"Page {token} out of range (1..{page_count}).")
    return n


def derive_output_path(input_path: str, suffix: str = "edited") -> str:
    """Return a sibling path `name-edited.pdf`, deduping if it already
    exists (`name-edited-2.pdf`, etc.). Caller can override but the
    default keeps the source untouched."""
    p = Path(input_path)
    base = p.with_name(f"{p.stem}-{suffix}{p.suffix}")
    if not base.exists():
        return str(base)
    i = 2
    while True:
        cand = p.with_name(f"{p.stem}-{suffix}-{i}{p.suffix}")
        if not cand.exists():
            return str(cand)
        i += 1


# ---------------------------------------------------------- operations --

def rotate_pages(input_path: str, output_path: str,
                 page_indices: list[int] | range, degrees: int) -> int:
    """Rotate the specified pages clockwise by `degrees` (a multiple
    of 90). Returns the number of pages written."""
    if degrees % 90 != 0:
        raise PdfEditError(f"Rotation must be a multiple of 90 (got {degrees}).")
    reader = _open_reader(input_path)
    indices = set(_validate_indices(page_indices, len(reader.pages)))
    writer = _new_writer()
    for i, page in enumerate(reader.pages):
        if i in indices:
            page.rotate(int(degrees))
        writer.add_page(page)
    _write(writer, output_path)
    return len(writer.pages)


def delete_pages(input_path: str, output_path: str,
                 page_indices: list[int]) -> int:
    """Remove the specified pages. At least one page must remain."""
    reader = _open_reader(input_path)
    drop = set(_validate_indices(page_indices, len(reader.pages)))
    if len(drop) >= len(reader.pages):
        raise PdfEditError("Refusing to delete every page (would leave an empty PDF).")
    writer = _new_writer()
    for i, page in enumerate(reader.pages):
        if i not in drop:
            writer.add_page(page)
    _write(writer, output_path)
    return len(writer.pages)


def extract_pages(input_path: str, output_path: str,
                  page_indices: list[int]) -> int:
    """Write a new PDF containing only the specified pages, in the
    order they appear in the list (duplicates allowed — useful for
    reorder use-cases)."""
    reader = _open_reader(input_path)
    # Don't dedupe — preserve caller's order so this can double as
    # the reorder primitive.
    for i in page_indices:
        if not 0 <= int(i) < len(reader.pages):
            raise PdfEditError(
                f"Page index {i} out of range (0..{len(reader.pages) - 1}).")
    if not page_indices:
        raise PdfEditError("No pages selected.")
    writer = _new_writer()
    for i in page_indices:
        writer.add_page(reader.pages[int(i)])
    _write(writer, output_path)
    return len(writer.pages)


def reorder_pages(input_path: str, output_path: str,
                  new_order: list[int]) -> int:
    """Write a new PDF with pages re-shuffled into `new_order`. The
    list must reference every original page exactly once (a true
    permutation). Use `extract_pages` for partial selections."""
    reader = _open_reader(input_path)
    n = len(reader.pages)
    if sorted(int(i) for i in new_order) != list(range(n)):
        raise PdfEditError(
            "Reorder requires a permutation of every page (0..N-1) "
            "exactly once. Use extract_pages for partial selections.")
    return extract_pages(input_path, output_path, list(new_order))


def merge_pdfs(input_paths: list[str], output_path: str) -> int:
    """Concatenate the listed PDFs into one. Order matches the
    input list. Returns the total page count of the merged PDF."""
    if not input_paths:
        raise PdfEditError("No input PDFs given.")
    writer = _new_writer()
    for path in input_paths:
        # Re-use _open_reader for its error handling, then append.
        reader = _open_reader(path)
        for page in reader.pages:
            writer.add_page(page)
    _write(writer, output_path)
    return len(writer.pages)


def insert_blank_page(input_path: str, output_path: str,
                       after_index: int,
                       width: float | None = None,
                       height: float | None = None) -> int:
    """Insert a blank page **after** `after_index` (0-based). Use
    `-1` to insert before page 0. Blank-page size defaults to the
    media-box of the page next to the insertion (so the new blank
    matches the document's existing page dimensions); falls back to
    US Letter (612 × 792 pt) for empty input."""
    reader = _open_reader(input_path)
    writer = _new_writer()
    n = len(reader.pages)
    if not -1 <= after_index < n:
        raise PdfEditError(
            f"after_index {after_index} out of range (-1..{n - 1}).")

    # Determine blank-page dimensions: caller wins; else clone from
    # the existing page next to the insertion; else US Letter.
    def _blank_dims() -> tuple[float, float]:
        if width and height:
            return float(width), float(height)
        ref = after_index if after_index >= 0 else 0
        if 0 <= ref < n:
            mbox = reader.pages[ref].mediabox
            return float(mbox.width), float(mbox.height)
        return 612.0, 792.0

    w, h = _blank_dims()
    if after_index < 0:
        writer.add_blank_page(width=w, height=h)
    for i, page in enumerate(reader.pages):
        writer.add_page(page)
        if i == after_index:
            writer.add_blank_page(width=w, height=h)
    _write(writer, output_path)
    return len(writer.pages)


# ---------------------------------------------------------- internals --

def _write(writer, output_path: str) -> None:
    """Serialise the writer to `output_path`, creating intermediate
    directories. Wraps the underlying I/O exceptions in PdfEditError."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            writer.write(f)
    except OSError as e:
        raise PdfEditError(f"Could not write PDF: {e}") from e

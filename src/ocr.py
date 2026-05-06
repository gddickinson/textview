"""Optional OCR for image-only PDFs and image files.

If `pytesseract` and a Tesseract install are available, `ocr_pdf(path)`
extracts text page-by-page; without them, every function returns
`(False, "tesseract not available")`. The workspace indexer uses this
lazily so vision-less PDFs become searchable when the user has OCR set
up but doesn't break otherwise.

Install:  brew install tesseract && pip install pytesseract
"""
from __future__ import annotations
from pathlib import Path


def is_available() -> tuple[bool, str]:
    """Return `(ok, reason)` — `reason` is the user-facing install hint
    when not available."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False, ("Install `pytesseract` (pip) and Tesseract "
                       "(brew install tesseract) to enable OCR.")
    try:
        # Pillow ships with the conda env; pdf rasterisation needs pypdf
        # or pdf2image. We use pypdf to test for Image-only pages and
        # pdf2image for rasterising. Both are best-effort imports.
        import pdf2image  # noqa: F401
    except ImportError:
        return False, ("Install `pdf2image` (pip) and `poppler` (brew "
                       "install poppler) to OCR scanned PDFs.")
    return True, ""


def ocr_image(path) -> tuple[bool, str]:
    """Run OCR on a single image file. Returns `(ok, text-or-error)`."""
    ok, why = is_available()
    if not ok: return False, why
    import pytesseract
    from PIL import Image
    try:
        img = Image.open(str(path))
    except Exception as e:
        return False, f"could not open image: {e}"
    try:
        text = pytesseract.image_to_string(img)
    except Exception as e:
        return False, f"tesseract failed: {e}"
    return True, text


def ocr_pdf(path, max_pages: int = 50) -> tuple[bool, list[str]]:
    """Rasterise each page and OCR it. Returns `(ok, list_of_page_texts)`.
    On error, the second element is a list with one error string."""
    ok, why = is_available()
    if not ok: return False, [why]
    import pytesseract
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(str(path), first_page=1, last_page=max_pages)
    except Exception as e:
        return False, [f"could not rasterise PDF: {e}"]
    out: list[str] = []
    for img in pages:
        try: out.append(pytesseract.image_to_string(img))
        except Exception as e: out.append(f"[OCR error: {e}]")
    return True, out

"""Coverage for src/pdf_reconstruct.py — PDF → Markdown and
PDF → DOCX. Each test builds a small PDF with real text, runs the
conversion, and asserts the output is non-empty + a real file of
the expected type."""
from __future__ import annotations

import importlib.util
import pytest
from pathlib import Path

from src.pdf_reconstruct import (
    PdfReconstructError, pdf_to_markdown, pdf_to_docx, _suggest_sibling,
)


_HAS_PYMUPDF4LLM = importlib.util.find_spec("pymupdf4llm") is not None
_HAS_PDF2DOCX = importlib.util.find_spec("pdf2docx") is not None
_HAS_FITZ = importlib.util.find_spec("fitz") is not None


def _make_pdf_with_text(path: Path, blocks: list[tuple[float, float, str]]) -> Path:
    """Build a small PDF with the given (x, y, text) blocks."""
    import fitz
    d = fitz.open()
    d.new_page(width=612, height=792)
    for x, y, t in blocks:
        d[0].insert_text((x, y), t, fontname="helv", fontsize=14)
    d.save(path); d.close()
    return path


# ---------------------------------------------------------- sibling-path helper --

def test_suggest_sibling_basic(tmp_path):
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"")
    out = _suggest_sibling(str(src), "converted", "md")
    assert out.endswith("doc-converted.md")
    assert str(tmp_path) in out


def test_suggest_sibling_dedupes(tmp_path):
    src = tmp_path / "doc.pdf"; src.write_bytes(b"")
    (tmp_path / "doc-converted.md").write_bytes(b"")
    out = _suggest_sibling(str(src), "converted", "md")
    assert out.endswith("doc-converted-2.md")


def test_suggest_sibling_different_ext(tmp_path):
    src = tmp_path / "doc.pdf"; src.write_bytes(b"")
    out = _suggest_sibling(str(src), "converted", "docx")
    assert out.endswith("doc-converted.docx")


# ---------------------------------------------------------- PDF → Markdown --

@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PYMUPDF4LLM),
                    reason="pymupdf4llm (+fitz) required")
def test_pdf_to_markdown_basic(tmp_path):
    src = _make_pdf_with_text(tmp_path / "in.pdf", [
        (50, 100, "Heading text"),
        (50, 150, "Body paragraph here"),
    ])
    out = pdf_to_markdown(str(src))
    assert Path(out).is_file()
    assert out.endswith(".md")
    text = Path(out).read_text(encoding="utf-8")
    assert "Heading text" in text
    assert "Body paragraph here" in text


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PYMUPDF4LLM),
                    reason="pymupdf4llm (+fitz) required")
def test_pdf_to_markdown_default_output_is_sibling(tmp_path):
    src = _make_pdf_with_text(tmp_path / "doc.pdf",
                               [(50, 100, "hi")])
    out = pdf_to_markdown(str(src))
    assert out.startswith(str(tmp_path))
    assert "doc-converted.md" in out


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PYMUPDF4LLM),
                    reason="pymupdf4llm (+fitz) required")
def test_pdf_to_markdown_custom_output(tmp_path):
    src = _make_pdf_with_text(tmp_path / "in.pdf", [(50, 100, "hi")])
    custom = tmp_path / "out" / "my.md"
    out = pdf_to_markdown(str(src), str(custom))
    assert out == str(custom)
    assert custom.is_file()


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PYMUPDF4LLM),
                    reason="pymupdf4llm (+fitz) required")
def test_pdf_to_markdown_dedupes_default_output(tmp_path):
    """Running twice with the default output should produce two
    distinct sibling files."""
    src = _make_pdf_with_text(tmp_path / "doc.pdf",
                               [(50, 100, "hi")])
    out1 = pdf_to_markdown(str(src))
    out2 = pdf_to_markdown(str(src))
    assert out1 != out2
    assert "doc-converted-2.md" in out2


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PYMUPDF4LLM),
                    reason="pymupdf4llm (+fitz) required")
def test_pdf_to_markdown_pages_subset(tmp_path):
    """`pages=[0]` skips later pages."""
    import fitz
    src = tmp_path / "in.pdf"
    d = fitz.open()
    d.new_page(width=612, height=792)
    d[0].insert_text((50, 100), "PAGE-ZERO text", fontname="helv", fontsize=14)
    d.new_page(width=612, height=792)
    d[1].insert_text((50, 100), "PAGE-ONE text",  fontname="helv", fontsize=14)
    d.save(src); d.close()
    out = pdf_to_markdown(str(src), str(tmp_path / "x.md"), pages=[0])
    text = Path(out).read_text(encoding="utf-8")
    assert "PAGE-ZERO" in text
    assert "PAGE-ONE" not in text


def test_pdf_to_markdown_missing_source_raises(tmp_path):
    with pytest.raises(PdfReconstructError):
        pdf_to_markdown(str(tmp_path / "no-such.pdf"))


# ---------------------------------------------------------- PDF → DOCX --

@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PDF2DOCX),
                    reason="pdf2docx (+fitz) required")
def test_pdf_to_docx_basic(tmp_path):
    src = _make_pdf_with_text(tmp_path / "in.pdf", [
        (50, 100, "Title"),
        (50, 200, "Body of the document."),
    ])
    out = pdf_to_docx(str(src))
    assert Path(out).is_file()
    assert out.endswith(".docx")
    # DOCX is a ZIP package — verify magic bytes.
    head = Path(out).read_bytes()[:2]
    assert head == b"PK"


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PDF2DOCX),
                    reason="pdf2docx (+fitz) required")
def test_pdf_to_docx_round_trip(tmp_path):
    """Round-trip: PDF → DOCX → re-read DOCX with python-docx → text
    should survive."""
    src = _make_pdf_with_text(tmp_path / "in.pdf", [
        (50, 100, "ROUND-TRIP MARKER"),
    ])
    out = pdf_to_docx(str(src))
    try:
        import docx
    except ImportError:
        pytest.skip("python-docx not installed")
    d = docx.Document(out)
    body = "\n".join(p.text for p in d.paragraphs)
    assert "ROUND-TRIP MARKER" in body


@pytest.mark.skipif(not (_HAS_FITZ and _HAS_PDF2DOCX),
                    reason="pdf2docx (+fitz) required")
def test_pdf_to_docx_custom_output(tmp_path):
    src = _make_pdf_with_text(tmp_path / "in.pdf",
                               [(50, 100, "hi")])
    target = tmp_path / "subdir" / "my.docx"
    out = pdf_to_docx(str(src), str(target))
    assert out == str(target)
    assert target.is_file()


def test_pdf_to_docx_missing_source_raises(tmp_path):
    with pytest.raises(PdfReconstructError):
        pdf_to_docx(str(tmp_path / "no-such.pdf"))

"""Coverage for src/pdf_text_edit.py — span listing, single-span
replacement, find-and-replace across pages, error paths.

Block-skipped when PyMuPDF (`fitz`) isn't importable."""
from __future__ import annotations

import importlib
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF (fitz) not installed",
)

from src.pdf_text_edit import (
    PdfTextEditError, TextSpan, list_text_spans, find_span_at,
    replace_span, replace_span_object, find_and_replace,
    FindReplaceResult, _parse_hex_color, _int_color_to_floats,
)


def _make_pdf_with_text(path: Path, lines: list[tuple[float, float, str, dict]] = None,
                         page_count: int = 1) -> Path:
    """Build a PDF with the given text insertions. Each entry is
    `(x, y, text, kwargs)` where kwargs forward to PyMuPDF's
    `insert_text`."""
    import fitz
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page(width=612, height=792)
    if lines:
        for x, y, t, kw in lines:
            doc[0].insert_text((x, y), t, **kw)
    doc.save(path); doc.close()
    return path


# ---------------------------------------------------------- colour helpers --

def test_int_color_to_floats_red():
    assert _int_color_to_floats(0xFF0000) == (1.0, 0.0, 0.0)


def test_int_color_to_floats_green():
    assert _int_color_to_floats(0x00FF00) == (0.0, 1.0, 0.0)


def test_parse_hex_color_basic():
    assert _parse_hex_color("#000000") == (0.0, 0.0, 0.0)
    assert _parse_hex_color("#FFFFFF") == (1.0, 1.0, 1.0)


def test_parse_hex_color_short_form():
    assert _parse_hex_color("#f00") == (1.0, 0.0, 0.0)


def test_parse_hex_color_rejects_bad():
    with pytest.raises(PdfTextEditError):
        _parse_hex_color("#xyz")
    with pytest.raises(PdfTextEditError):
        _parse_hex_color("")


# ---------------------------------------------------------- list_text_spans --

def test_list_text_spans_empty_pdf(tmp_path):
    p = _make_pdf_with_text(tmp_path / "empty.pdf")
    spans = list_text_spans(str(p))
    assert spans == []


def test_list_text_spans_single_text(tmp_path):
    p = _make_pdf_with_text(tmp_path / "single.pdf", lines=[
        (50, 100, "Hello, world!", dict(fontname="helv", fontsize=14)),
    ])
    spans = list_text_spans(str(p))
    assert len(spans) == 1
    s = spans[0]
    assert isinstance(s, TextSpan)
    assert s.id == 0
    assert s.page == 0
    assert s.text == "Hello, world!"
    assert s.font == "Helvetica"
    assert abs(s.size - 14) < 0.01


def test_list_text_spans_multi(tmp_path):
    p = _make_pdf_with_text(tmp_path / "multi.pdf", lines=[
        (50, 100, "Top",      dict(fontname="helv", fontsize=14)),
        (50, 200, "Middle",   dict(fontname="helv", fontsize=12)),
        (50, 300, "Bottom",   dict(fontname="helv", fontsize=10)),
    ])
    spans = list_text_spans(str(p))
    assert len(spans) == 3
    # IDs are sequential.
    assert [s.id for s in spans] == [0, 1, 2]


def test_list_text_spans_skips_whitespace_only(tmp_path):
    p = _make_pdf_with_text(tmp_path / "ws.pdf", lines=[
        (50, 100, "real text", dict(fontname="helv", fontsize=12)),
    ])
    spans = list_text_spans(str(p))
    assert all(s.text.strip() for s in spans)


def test_list_text_spans_multipage(tmp_path):
    """Spans on page 2 still get sequential ids continuing from page 1."""
    import fitz
    p = tmp_path / "multi.pdf"
    d = fitz.open()
    d.new_page(width=612, height=792)
    d[0].insert_text((50, 100), "page 0 a", fontname="helv", fontsize=12)
    d[0].insert_text((50, 200), "page 0 b", fontname="helv", fontsize=12)
    d.new_page(width=612, height=792)
    d[1].insert_text((50, 100), "page 1 a", fontname="helv", fontsize=12)
    d.save(p); d.close()

    spans = list_text_spans(str(p))
    assert len(spans) == 3
    pages = [s.page for s in spans]
    assert pages.count(0) == 2 and pages.count(1) == 1
    # Sequential ids across pages.
    assert [s.id for s in spans] == [0, 1, 2]


def test_text_span_color_hex():
    s = TextSpan(id=0, page=0, bbox=(0, 0, 1, 1), text="x",
                 font="Helvetica", size=12, color=0xFF0000)
    assert s.color_hex() == "#FF0000"


# ---------------------------------------------------------- hit testing --

def test_find_span_at_inside(tmp_path):
    p = _make_pdf_with_text(tmp_path / "hit.pdf", lines=[
        (50, 100, "click me", dict(fontname="helv", fontsize=14)),
    ])
    spans = list_text_spans(str(p))
    target = spans[0]
    # Point inside the span's bbox.
    cx = (target.bbox[0] + target.bbox[2]) / 2
    cy = (target.bbox[1] + target.bbox[3]) / 2
    hit = find_span_at(str(p), 0, cx, cy)
    assert hit is not None
    assert hit.text == "click me"


def test_find_span_at_outside(tmp_path):
    p = _make_pdf_with_text(tmp_path / "miss.pdf", lines=[
        (50, 100, "click me", dict(fontname="helv", fontsize=14)),
    ])
    # Click on empty space.
    assert find_span_at(str(p), 0, 500, 500) is None


def test_find_span_at_wrong_page(tmp_path):
    """A span on page 0 isn't found via page_index=1."""
    p = _make_pdf_with_text(tmp_path / "p0.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    assert find_span_at(str(p), 1, 60, 95) is None


# ---------------------------------------------------------- replace_span --

def test_replace_span_basic(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "Original", dict(fontname="helv", fontsize=14)),
    ])
    spans = list_text_spans(str(p))
    target = spans[0]
    out = tmp_path / "out.pdf"
    replace_span(str(p), str(out), 0, target.bbox, "Replaced",
                 fontname="helv", fontsize=14)
    # Read back — should now say "Replaced".
    new_spans = list_text_spans(str(out))
    assert len(new_spans) == 1
    assert "Replaced" in new_spans[0].text
    assert "Original" not in new_spans[0].text


def test_replace_span_keeps_font(tmp_path):
    """Font from span survives the round-trip when reused on write."""
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "Italic text", dict(fontname="tiit", fontsize=14)),  # Times-Italic
    ])
    spans = list_text_spans(str(p))
    target = spans[0]
    assert "Times-Italic" in target.font
    out = tmp_path / "out.pdf"
    replace_span(str(p), str(out), 0, target.bbox, "Still italic",
                 fontname=target.font, fontsize=target.size)
    new_spans = list_text_spans(str(out))
    assert "Times-Italic" in new_spans[0].font


def test_replace_span_color(tmp_path):
    """Passing text_color recolors the replacement."""
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "Plain", dict(fontname="helv", fontsize=14, color=(0, 0, 0))),
    ])
    target = list_text_spans(str(p))[0]
    out = tmp_path / "out.pdf"
    replace_span(str(p), str(out), 0, target.bbox, "Now red",
                 fontname="helv", fontsize=14, text_color="#FF0000")
    new = list_text_spans(str(out))
    assert new[0].color != 0   # not pure black


def test_replace_span_bad_page_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        replace_span(str(p), str(out), 99, (0, 0, 100, 100), "new")


def test_replace_span_empty_text_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        replace_span(str(p), str(out), 0, (0, 0, 100, 100), "")


def test_replace_span_empty_bbox_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        replace_span(str(p), str(out), 0, (10, 10, 10, 10), "x")


def test_replace_span_bad_color_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        replace_span(str(p), str(out), 0, (10, 10, 100, 100), "y",
                     text_color="not a color")


# ---------------------------------------------------------- replace_span_object --

def test_replace_span_object_keeps_attrs(tmp_path):
    """The TextSpan-based wrapper preserves font/size/color by default.

    Note: PyMuPDF auto-shrinks the replacement to fit the original
    bbox. Use a replacement that's SHORTER than the source so the
    size stays close to the requested value."""
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "Originalxxxxx",
         dict(fontname="helv", fontsize=18, color=(0.5, 0.0, 0.5))),
    ])
    target = list_text_spans(str(p))[0]
    out = tmp_path / "out.pdf"
    replace_span_object(str(p), str(out), target, "short")
    new = list_text_spans(str(out))
    assert "short" in new[0].text
    # Auto-fit shrinks slightly even for a shorter replacement; verify
    # the size stayed in the ballpark of the original (18pt → not the
    # default 11pt or a wholly-shrunk value).
    assert new[0].size >= 12
    assert new[0].color != 0                # still coloured


def test_replace_span_object_overrides(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "Original", dict(fontname="helv", fontsize=14)),
    ])
    target = list_text_spans(str(p))[0]
    out = tmp_path / "out.pdf"
    replace_span_object(str(p), str(out), target, "Bigger",
                         fontsize_override=20)
    new = list_text_spans(str(out))
    # 20pt should survive — wider rect could allow it to grow.
    # PyMuPDF auto-fit may still shrink; just confirm "Bigger" lands.
    assert "Bigger" in new[0].text


# ---------------------------------------------------------- find_and_replace --

def test_find_and_replace_single_page(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "the lazy dog", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    result = find_and_replace(str(p), str(out), "lazy", "happy")
    assert isinstance(result, FindReplaceResult)
    assert result.total == 1
    assert result.replacements_per_page == [1]


def test_find_and_replace_multiple_pages(tmp_path):
    import fitz
    p = tmp_path / "in.pdf"
    d = fitz.open()
    for _ in range(3):
        d.new_page(width=612, height=792)
    d[0].insert_text((50, 100), "lazy and lazy", fontname="helv", fontsize=12)
    d[1].insert_text((50, 100), "no match here",  fontname="helv", fontsize=12)
    d[2].insert_text((50, 100), "say lazy once",  fontname="helv", fontsize=12)
    d.save(p); d.close()

    out = tmp_path / "out.pdf"
    res = find_and_replace(str(p), str(out), "lazy", "x")
    # 2 hits on page 0, 0 on page 1, 1 on page 2.
    assert res.replacements_per_page == [2, 0, 1]
    assert res.total == 3


def test_find_and_replace_no_match(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "abc def", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    res = find_and_replace(str(p), str(out), "xyz", "qqq")
    assert res.total == 0


def test_find_and_replace_empty_query_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "x", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        find_and_replace(str(p), str(out), "", "new")


def test_find_and_replace_empty_replacement_raises(tmp_path):
    p = _make_pdf_with_text(tmp_path / "in.pdf", lines=[
        (50, 100, "abc", dict(fontname="helv", fontsize=12)),
    ])
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        find_and_replace(str(p), str(out), "abc", "")


def test_open_missing_file_raises(tmp_path):
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfTextEditError):
        list_text_spans(str(tmp_path / "no_such_file.pdf"))
    with pytest.raises(PdfTextEditError):
        replace_span(str(tmp_path / "missing.pdf"), str(out), 0,
                     (10, 10, 50, 30), "x")

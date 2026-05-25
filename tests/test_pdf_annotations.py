"""Coverage for src/pdf_annotations.py — every annotation type
round-tripped through PyMuPDF read-back. Each test builds a fresh
PDF, applies an annotation, reopens it via `list_annotations`, and
asserts the result.

Block-skipped when PyMuPDF isn't installed."""
from __future__ import annotations

import importlib
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fitz") is None,
    reason="PyMuPDF (fitz) not installed",
)

from src.pdf_annotations import (
    PdfAnnotationError, page_size, list_annotations,
    add_sticky_note, add_freetext, add_highlight, add_underline,
    add_strikeout, add_rectangle, add_circle, add_ink,
    delete_annotations, clear_annotations,
    _parse_hex_color, _validate_rect,
)


def _make_pdf(path: Path, page_count: int = 2) -> Path:
    """Use pypdf (the lighter dep) to write blank pages quickly."""
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(page_count):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)
    return path


# ---------------------------------------------------------- introspection --

def test_page_size(tmp_path):
    p = _make_pdf(tmp_path / "in.pdf", page_count=1)
    w, h = page_size(str(p), 0)
    assert (w, h) == (612.0, 792.0)


def test_page_size_out_of_range(tmp_path):
    p = _make_pdf(tmp_path / "in.pdf", page_count=1)
    with pytest.raises(PdfAnnotationError):
        page_size(str(p), 5)


def test_list_annotations_empty(tmp_path):
    p = _make_pdf(tmp_path / "in.pdf", page_count=2)
    assert list_annotations(str(p)) == []


# ---------------------------------------------------------- color parsing --

def test_parse_hex_color_full():
    assert _parse_hex_color("#ff0000") == (1.0, 0.0, 0.0)
    assert _parse_hex_color("#00ff00") == (0.0, 1.0, 0.0)
    assert _parse_hex_color("#0000ff") == (0.0, 0.0, 1.0)


def test_parse_hex_color_short():
    # `#f00` should expand to `#ff0000`.
    assert _parse_hex_color("#f00") == (1.0, 0.0, 0.0)


def test_parse_hex_color_no_hash():
    assert _parse_hex_color("ff0000") == (1.0, 0.0, 0.0)


def test_parse_hex_color_bad():
    with pytest.raises(PdfAnnotationError):
        _parse_hex_color("#xyz")
    with pytest.raises(PdfAnnotationError):
        _parse_hex_color("#1234")  # wrong length
    with pytest.raises(PdfAnnotationError):
        _parse_hex_color("")


def test_validate_rect_basic():
    assert _validate_rect((1, 2, 3, 4)) == (1.0, 2.0, 3.0, 4.0)


def test_validate_rect_bad_size():
    with pytest.raises(PdfAnnotationError):
        _validate_rect((1, 2, 0, 4))  # zero width
    with pytest.raises(PdfAnnotationError):
        _validate_rect((1, 2, -1, 4))


def test_validate_rect_wrong_shape():
    with pytest.raises(PdfAnnotationError):
        _validate_rect((1, 2, 3))  # too few elements
    with pytest.raises(PdfAnnotationError):
        _validate_rect("not a tuple")


# ---------------------------------------------------------- sticky note --

def test_add_sticky_note(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_sticky_note(str(src), str(out), 0, 100, 200, "Review this paragraph")
    anns = list_annotations(str(out))
    assert len(anns) == 1
    assert anns[0]["page"] == 0
    assert "Text" in anns[0]["type"]
    assert anns[0]["content"] == "Review this paragraph"


def test_sticky_note_on_second_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    add_sticky_note(str(src), str(out), 2, 50, 50, "second page note")
    anns = list_annotations(str(out))
    assert anns[0]["page"] == 2


def test_sticky_note_bad_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=1)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        add_sticky_note(str(src), str(out), 5, 100, 100, "x")


# ---------------------------------------------------------- free text --

def test_add_freetext(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_freetext(str(src), str(out), 0, (50, 50, 200, 30),
                 "Headline text", font_size=14, color="#0000FF")
    anns = list_annotations(str(out))
    assert len(anns) == 1
    assert "FreeText" in anns[0]["type"]


def test_add_freetext_with_fill(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_freetext(str(src), str(out), 0, (50, 50, 200, 30),
                 "Highlighted", color="#000000", fill="#FFFF00")
    anns = list_annotations(str(out))
    assert len(anns) == 1


# ---------------------------------------------------------- highlight / underline / strikeout --

def test_add_highlight(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_highlight(str(src), str(out), 0, (100, 100, 150, 20))
    anns = list_annotations(str(out))
    assert len(anns) == 1
    assert "Highlight" in anns[0]["type"]


def test_add_underline(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_underline(str(src), str(out), 0, (100, 100, 150, 20))
    anns = list_annotations(str(out))
    assert "Underline" in anns[0]["type"]


def test_add_strikeout(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_strikeout(str(src), str(out), 0, (100, 100, 150, 20))
    anns = list_annotations(str(out))
    assert "StrikeOut" in anns[0]["type"]


def test_highlight_bad_rect_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        add_highlight(str(src), str(out), 0, (100, 100, -50, 20))


def test_highlight_bad_color_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        add_highlight(str(src), str(out), 0, (100, 100, 50, 20), color="not-a-color")


# ---------------------------------------------------------- shapes --

def test_add_rectangle(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_rectangle(str(src), str(out), 0, (100, 100, 200, 50),
                  color="#FF0000", fill="#FFCCCC")
    anns = list_annotations(str(out))
    assert "Square" in anns[0]["type"] or "Rect" in anns[0]["type"]


def test_add_circle(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_circle(str(src), str(out), 0, (100, 100, 200, 50))
    anns = list_annotations(str(out))
    assert "Circle" in anns[0]["type"]


# ---------------------------------------------------------- ink --

def test_add_ink_single_stroke(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_ink(str(src), str(out), 0,
            [[(100, 100), (150, 120), (200, 140)]])
    anns = list_annotations(str(out))
    assert "Ink" in anns[0]["type"]


def test_add_ink_multiple_strokes(tmp_path):
    """Multi-stroke ink represents pen-lift between strokes."""
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    add_ink(str(src), str(out), 0,
            [[(100, 100), (110, 110)],
             [(200, 200), (210, 210), (220, 220)]])
    anns = list_annotations(str(out))
    assert len(anns) == 1


def test_add_ink_empty_strokes_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        add_ink(str(src), str(out), 0, [])
    with pytest.raises(PdfAnnotationError):
        add_ink(str(src), str(out), 0, [[]])


# ---------------------------------------------------------- delete --

def test_delete_one_annotation(tmp_path):
    """Build a PDF with 3 annotations, delete the middle one."""
    src = _make_pdf(tmp_path / "in.pdf")
    step1 = tmp_path / "step1.pdf"
    step2 = tmp_path / "step2.pdf"
    step3 = tmp_path / "step3.pdf"
    add_sticky_note(str(src), str(step1), 0, 50, 50, "first")
    add_sticky_note(str(step1), str(step2), 0, 100, 100, "second")
    add_sticky_note(str(step2), str(step3), 0, 200, 200, "third")
    assert len(list_annotations(str(step3))) == 3

    out = tmp_path / "out.pdf"
    n = delete_annotations(str(step3), str(out), [1])
    assert n == 1
    remaining = list_annotations(str(out))
    assert len(remaining) == 2
    contents = sorted(a["content"] for a in remaining)
    assert contents == ["first", "third"]


def test_delete_multiple(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    step1 = tmp_path / "1.pdf"; step2 = tmp_path / "2.pdf"; step3 = tmp_path / "3.pdf"
    add_sticky_note(str(src), str(step1), 0, 10, 10, "A")
    add_sticky_note(str(step1), str(step2), 0, 20, 20, "B")
    add_sticky_note(str(step2), str(step3), 0, 30, 30, "C")
    out = tmp_path / "out.pdf"
    n = delete_annotations(str(step3), str(out), [0, 2])
    assert n == 2
    assert {a["content"] for a in list_annotations(str(out))} == {"B"}


def test_delete_empty_indices_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        delete_annotations(str(src), str(out), [])


# ---------------------------------------------------------- clear --

def test_clear_all_annotations(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    step1 = tmp_path / "1.pdf"; step2 = tmp_path / "2.pdf"
    add_sticky_note(str(src), str(step1), 0, 50, 50, "p1")
    add_sticky_note(str(step1), str(step2), 1, 60, 60, "p2")
    assert len(list_annotations(str(step2))) == 2

    out = tmp_path / "out.pdf"
    n = clear_annotations(str(step2), str(out))
    assert n == 2
    assert list_annotations(str(out)) == []


def test_clear_one_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    step1 = tmp_path / "1.pdf"; step2 = tmp_path / "2.pdf"
    add_sticky_note(str(src), str(step1), 0, 50, 50, "keep me page 0")
    add_sticky_note(str(step1), str(step2), 1, 60, 60, "drop me page 1")

    out = tmp_path / "out.pdf"
    n = clear_annotations(str(step2), str(out), page_index=1)
    assert n == 1
    rem = list_annotations(str(out))
    assert len(rem) == 1
    assert rem[0]["page"] == 0


def test_clear_bad_page_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        clear_annotations(str(src), str(out), page_index=99)


# ---------------------------------------------------------- list ordering --

def test_list_annotations_walks_all_pages(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    step1 = tmp_path / "1.pdf"; step2 = tmp_path / "2.pdf"; step3 = tmp_path / "3.pdf"
    add_sticky_note(str(src), str(step1), 0, 10, 10, "p0a")
    add_sticky_note(str(step1), str(step2), 2, 20, 20, "p2a")
    add_sticky_note(str(step2), str(step3), 1, 30, 30, "p1a")
    anns = list_annotations(str(step3))
    assert len(anns) == 3
    pages_seen = {a["page"] for a in anns}
    assert pages_seen == {0, 1, 2}
    # `index` field is sequential, used by delete_annotations.
    indices = sorted(a["index"] for a in anns)
    assert indices == [0, 1, 2]


# ---------------------------------------------------------- file errors --

def test_open_missing_file_raises(tmp_path):
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfAnnotationError):
        add_sticky_note(str(tmp_path / "nope.pdf"), str(out), 0, 0, 0, "x")

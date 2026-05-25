"""Coverage for src/pdf_editor.py — every page operation, every
error path, plus the page-range parser and sibling-path helper.

Each test builds a fresh multi-page PDF with `pypdf` so the round-trip
goes through the real library."""
from __future__ import annotations

import io
import pytest
from pathlib import Path

from src.pdf_editor import (
    PdfEditError, parse_page_range, derive_output_path,
    rotate_pages, delete_pages, extract_pages, reorder_pages,
    merge_pdfs, insert_blank_page,
)


def _make_pdf(path: Path, page_count: int, *, page_size=(612, 792)) -> Path:
    """Write a `page_count`-page PDF to `path`. Pages are blank but
    have distinct sizes so reorder tests can identify them. Returns
    the path."""
    from pypdf import PdfWriter
    w = PdfWriter()
    for i in range(page_count):
        # Vary width slightly per page so we can detect order.
        w.add_blank_page(width=page_size[0] + i, height=page_size[1])
    with open(path, "wb") as f:
        w.write(f)
    return path


def _read_page_widths(path: Path) -> list[int]:
    from pypdf import PdfReader
    r = PdfReader(str(path))
    return [int(p.mediabox.width) for p in r.pages]


def _read_page_rotations(path: Path) -> list[int]:
    """Per-page /Rotate values (0 if absent)."""
    from pypdf import PdfReader
    r = PdfReader(str(path))
    out = []
    for p in r.pages:
        rot = p.get("/Rotate", 0)
        out.append(int(rot) % 360)
    return out


# ---------------------------------------------------------- parse_page_range --

def test_parse_single_page():
    assert parse_page_range("1", 5) == [0]
    assert parse_page_range("5", 5) == [4]


def test_parse_multiple_pages():
    assert parse_page_range("1,3,5", 5) == [0, 2, 4]


def test_parse_range():
    assert parse_page_range("1-3", 5) == [0, 1, 2]
    assert parse_page_range("2-5", 5) == [1, 2, 3, 4]


def test_parse_mixed():
    assert parse_page_range("1-3,7,10-12", 12) == [0, 1, 2, 6, 9, 10, 11]


def test_parse_end_keyword():
    assert parse_page_range("end", 5) == [4]
    assert parse_page_range("3-end", 5) == [2, 3, 4]


def test_parse_dedupe():
    """A duplicate page in input collapses to one entry."""
    assert parse_page_range("1,1,2", 5) == [0, 1]
    assert parse_page_range("1-3,2,3", 5) == [0, 1, 2]


def test_parse_out_of_range():
    with pytest.raises(PdfEditError):
        parse_page_range("10", 5)


def test_parse_reversed_range_rejects():
    with pytest.raises(PdfEditError):
        parse_page_range("5-2", 10)


def test_parse_empty_rejects():
    with pytest.raises(PdfEditError):
        parse_page_range("", 5)
    with pytest.raises(PdfEditError):
        parse_page_range("   ", 5)


def test_parse_bad_token_rejects():
    with pytest.raises(PdfEditError):
        parse_page_range("foo", 5)
    with pytest.raises(PdfEditError):
        parse_page_range("1-bar", 5)


# ---------------------------------------------------------- derive_output_path --

def test_derive_output_path_basic(tmp_path):
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"")
    out = derive_output_path(str(src))
    assert out.endswith("doc-edited.pdf")


def test_derive_output_path_dedupes(tmp_path):
    """When `name-edited.pdf` exists, the helper picks
    `name-edited-2.pdf`, then `name-edited-3.pdf`, etc."""
    src = tmp_path / "doc.pdf"; src.write_bytes(b"")
    (tmp_path / "doc-edited.pdf").write_bytes(b"")
    out = derive_output_path(str(src))
    assert out.endswith("doc-edited-2.pdf")
    (tmp_path / "doc-edited-2.pdf").write_bytes(b"")
    out2 = derive_output_path(str(src))
    assert out2.endswith("doc-edited-3.pdf")


def test_derive_output_path_custom_suffix(tmp_path):
    src = tmp_path / "doc.pdf"; src.write_bytes(b"")
    out = derive_output_path(str(src), suffix="rotated")
    assert out.endswith("doc-rotated.pdf")


# ---------------------------------------------------------- rotate --

def test_rotate_single_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    n = rotate_pages(str(src), str(out), [1], 90)
    assert n == 3
    rots = _read_page_rotations(out)
    assert rots == [0, 90, 0]


def test_rotate_multiple_pages_270(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=4)
    out = tmp_path / "out.pdf"
    rotate_pages(str(src), str(out), [0, 3], 270)
    rots = _read_page_rotations(out)
    assert rots == [270, 0, 0, 270]


def test_rotate_180(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    out = tmp_path / "out.pdf"
    rotate_pages(str(src), str(out), [0, 1], 180)
    assert _read_page_rotations(out) == [180, 180]


def test_rotate_bad_angle_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=1)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        rotate_pages(str(src), str(out), [0], 45)


def test_rotate_out_of_range_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=1)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        rotate_pages(str(src), str(out), [5], 90)


# ---------------------------------------------------------- delete --

def test_delete_one_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out = tmp_path / "out.pdf"
    n = delete_pages(str(src), str(out), [2])
    assert n == 4
    # Page widths: 612, 613, 614, 615, 616 — drop index 2 (614).
    assert _read_page_widths(out) == [612, 613, 615, 616]


def test_delete_multiple_pages(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=6)
    out = tmp_path / "out.pdf"
    delete_pages(str(src), str(out), [0, 3, 5])
    assert _read_page_widths(out) == [613, 614, 616]


def test_delete_all_pages_refused(tmp_path):
    """Deleting every page would leave an empty PDF — refuse."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        delete_pages(str(src), str(out), [0, 1, 2])


def test_delete_out_of_range_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        delete_pages(str(src), str(out), [5])


# ---------------------------------------------------------- extract --

def test_extract_range(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out = tmp_path / "out.pdf"
    n = extract_pages(str(src), str(out), [1, 2, 3])
    assert n == 3
    assert _read_page_widths(out) == [613, 614, 615]


def test_extract_preserves_caller_order(tmp_path):
    """Unlike delete, extract preserves whatever order the caller
    asked for — so it can double as reorder."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=4)
    out = tmp_path / "out.pdf"
    extract_pages(str(src), str(out), [3, 0, 2, 1])
    assert _read_page_widths(out) == [615, 612, 614, 613]


def test_extract_empty_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        extract_pages(str(src), str(out), [])


def test_extract_out_of_range_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        extract_pages(str(src), str(out), [0, 99])


# ---------------------------------------------------------- reorder --

def test_reorder_full_permutation(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=4)
    out = tmp_path / "out.pdf"
    reorder_pages(str(src), str(out), [3, 1, 0, 2])
    assert _read_page_widths(out) == [615, 613, 612, 614]


def test_reorder_rejects_partial(tmp_path):
    """Reorder requires every page once; missing pages → error."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=4)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        reorder_pages(str(src), str(out), [0, 1])  # missing 2, 3


def test_reorder_rejects_dupes(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        reorder_pages(str(src), str(out), [0, 0, 1])


# ---------------------------------------------------------- merge --

def test_merge_two_pdfs(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", page_count=2)
    b = _make_pdf(tmp_path / "b.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    n = merge_pdfs([str(a), str(b)], str(out))
    assert n == 5


def test_merge_preserves_order(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", page_count=2, page_size=(100, 200))
    b = _make_pdf(tmp_path / "b.pdf", page_count=2, page_size=(300, 400))
    out = tmp_path / "out.pdf"
    merge_pdfs([str(a), str(b)], str(out))
    # a's pages 100, 101 then b's pages 300, 301
    assert _read_page_widths(out) == [100, 101, 300, 301]


def test_merge_empty_input_raises(tmp_path):
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        merge_pdfs([], str(out))


def test_merge_one_pdf_is_a_copy(tmp_path):
    """Edge case: merge of a single PDF still works."""
    a = _make_pdf(tmp_path / "a.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    n = merge_pdfs([str(a)], str(out))
    assert n == 3


# ---------------------------------------------------------- insert_blank --

def test_insert_blank_after_middle(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out = tmp_path / "out.pdf"
    n = insert_blank_page(str(src), str(out), after_index=0)
    assert n == 4
    # Page widths: 612, *blank (matches page 0 width = 612)*, 613, 614
    widths = _read_page_widths(out)
    assert widths[0] == 612
    assert widths[2] == 613 and widths[3] == 614


def test_insert_blank_at_start(tmp_path):
    """after_index=-1 inserts before page 0."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    out = tmp_path / "out.pdf"
    n = insert_blank_page(str(src), str(out), after_index=-1)
    assert n == 3
    # Blank inherits page 0's dims (612); then page 0 (612) then page 1 (613)
    assert _read_page_widths(out) == [612, 612, 613]


def test_insert_blank_at_end(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=2)
    out = tmp_path / "out.pdf"
    insert_blank_page(str(src), str(out), after_index=1)
    widths = _read_page_widths(out)
    assert len(widths) == 3
    # Blank inherits page 1's dims (613).
    assert widths == [612, 613, 613]


def test_insert_blank_explicit_dims(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=1)
    out = tmp_path / "out.pdf"
    insert_blank_page(str(src), str(out), after_index=0, width=200, height=300)
    widths = _read_page_widths(out)
    assert widths == [612, 200]


def test_insert_blank_out_of_range_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=1)
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        insert_blank_page(str(src), str(out), after_index=10)
    with pytest.raises(PdfEditError):
        insert_blank_page(str(src), str(out), after_index=-2)


# ---------------------------------------------------------- error paths --

def test_open_missing_file_raises(tmp_path):
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        rotate_pages(str(tmp_path / "nope.pdf"), str(out), [0], 90)


# ---------------------------------------------------------- split --

from src.pdf_editor import split_pdf, derive_output_path_in


def test_split_every_page(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out_dir = tmp_path / "out"
    paths = split_pdf(str(src), str(out_dir))
    assert len(paths) == 5
    # Each output has exactly one page.
    for p in paths:
        widths = _read_page_widths(Path(p))
        assert len(widths) == 1


def test_split_every_n(tmp_path):
    """5-page PDF split every 2 pages → 3 files (2 + 2 + 1)."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out_dir = tmp_path / "out"
    paths = split_pdf(str(src), str(out_dir), mode="every_n", every_n=2)
    assert len(paths) == 3
    widths = [_read_page_widths(Path(p)) for p in paths]
    assert [len(w) for w in widths] == [2, 2, 1]


def test_split_boundaries(tmp_path):
    """15-page split at boundaries [5, 10] → 3 files (1-5, 6-10, 11-15)."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=15)
    out_dir = tmp_path / "out"
    paths = split_pdf(str(src), str(out_dir),
                       mode="boundaries", boundaries=[5, 10])
    assert len(paths) == 3
    counts = [len(_read_page_widths(Path(p))) for p in paths]
    assert counts == [5, 5, 5]


def test_split_boundaries_unsorted_input(tmp_path):
    """The boundaries list is sorted before use, so [10, 5] is the
    same as [5, 10]."""
    src = _make_pdf(tmp_path / "in.pdf", page_count=15)
    out_dir = tmp_path / "out"
    paths = split_pdf(str(src), str(out_dir),
                       mode="boundaries", boundaries=[10, 5])
    counts = [len(_read_page_widths(Path(p))) for p in paths]
    assert counts == [5, 5, 5]


def test_split_boundaries_out_of_range_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out_dir = tmp_path / "out"
    with pytest.raises(PdfEditError):
        split_pdf(str(src), str(out_dir),
                  mode="boundaries", boundaries=[10])


def test_split_boundaries_empty_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=5)
    out_dir = tmp_path / "out"
    with pytest.raises(PdfEditError):
        split_pdf(str(src), str(out_dir),
                  mode="boundaries", boundaries=[])


def test_split_unknown_mode_raises(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out_dir = tmp_path / "out"
    with pytest.raises(PdfEditError):
        split_pdf(str(src), str(out_dir), mode="bananas")


def test_split_every_n_validates(tmp_path):
    src = _make_pdf(tmp_path / "in.pdf", page_count=3)
    out_dir = tmp_path / "out"
    with pytest.raises(PdfEditError):
        split_pdf(str(src), str(out_dir), mode="every_n", every_n=0)


def test_split_custom_template(tmp_path):
    """`filename_template` controls output naming."""
    src = _make_pdf(tmp_path / "doc.pdf", page_count=3)
    out_dir = tmp_path / "out"
    paths = split_pdf(str(src), str(out_dir),
                       filename_template="{stem}_p{idx}{ext}")
    assert all(Path(p).name in ("doc_p1.pdf", "doc_p2.pdf", "doc_p3.pdf")
               for p in paths)


def test_split_dedupes_existing_files(tmp_path):
    """If `name.pdf` already exists, the split adds `-2`, `-3`, …
    so a re-run never clobbers a previous split."""
    src = _make_pdf(tmp_path / "doc.pdf", page_count=2)
    out_dir = tmp_path / "out"
    # Run twice. The second call should pick up `-2` suffix paths.
    paths1 = split_pdf(str(src), str(out_dir))
    paths2 = split_pdf(str(src), str(out_dir))
    assert set(paths1).isdisjoint(set(paths2)), \
        f"second split clobbered first: {paths1=} {paths2=}"


def test_split_missing_input_raises(tmp_path):
    out_dir = tmp_path / "out"
    with pytest.raises(PdfEditError):
        split_pdf(str(tmp_path / "nope.pdf"), str(out_dir))


def test_derive_output_path_in_basic(tmp_path):
    p = derive_output_path_in(tmp_path, "doc.pdf")
    assert p.endswith("doc.pdf")


def test_derive_output_path_in_dedupes(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"")
    p = derive_output_path_in(tmp_path, "doc.pdf")
    assert p.endswith("doc-2.pdf")


def test_open_corrupt_pdf_raises(tmp_path):
    p = tmp_path / "junk.pdf"
    p.write_bytes(b"not a pdf at all")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfEditError):
        delete_pages(str(p), str(out), [0])

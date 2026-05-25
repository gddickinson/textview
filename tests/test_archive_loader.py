"""Coverage for `src.archive_loader` — zip + tar listing, extraction,
path-traversal defence, file_loader integration."""
from __future__ import annotations

import io
import tarfile
import zipfile
import pytest
from pathlib import Path

from src.archive_loader import (
    is_supported, list_supported_extensions, list_members,
    render_listing_markdown, extract_member, extract_all,
    Member, ArchiveReadError, _kind, _safe_join,
)


# -- detection -------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "a.zip", "a.tar", "a.tar.gz", "a.tgz", "a.tar.bz2", "a.tbz2",
    "a.tar.xz", "a.txz", "a.7z", "a.jar", "a.war", "a.apk",
])
def test_is_supported(name):
    assert is_supported(name)


def test_is_supported_negatives():
    assert not is_supported("a.csv")
    assert not is_supported("a.docx")
    assert not is_supported("a.gz")  # bare .gz isn't an archive
    assert not is_supported("a")


def test_kind_compound_extensions():
    assert _kind("foo.tar.gz") == "tar"
    assert _kind("foo.tar.bz2") == "tar"
    assert _kind("foo.tar.xz") == "tar"
    assert _kind("foo.zip") == "zip"
    assert _kind("foo.7z") == "7z"
    assert _kind("foo.txt") is None


def test_supported_extensions_list_shape():
    exts = list_supported_extensions()
    assert all(e.startswith(".") for e in exts)
    assert ".zip" in exts and ".7z" in exts


# -- safe-join (path-traversal defence) ------------------------------------

def test_safe_join_rejects_absolute(tmp_path):
    with pytest.raises(ArchiveReadError):
        _safe_join(tmp_path, "/etc/passwd")


def test_safe_join_rejects_dotdot(tmp_path):
    with pytest.raises(ArchiveReadError):
        _safe_join(tmp_path, "../../../etc/passwd")
    with pytest.raises(ArchiveReadError):
        _safe_join(tmp_path, "a/../../../etc/passwd")


def test_safe_join_allows_subpath(tmp_path):
    result = _safe_join(tmp_path, "dir/file.txt")
    assert str(result).startswith(str(tmp_path))


# -- zip listing + extract -------------------------------------------------

@pytest.fixture
def sample_zip(tmp_path):
    p = tmp_path / "sample.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("hello.txt", "hi\n")
        zf.writestr("dir/inside.txt", "deeper\n")
        zf.writestr("empty_dir/", "")  # directory entry
    return p


def test_zip_list_members(sample_zip):
    members = list_members(str(sample_zip))
    names = sorted(m.name for m in members)
    assert "hello.txt" in names
    assert "dir/inside.txt" in names
    # `Member` dataclass shape
    hello = next(m for m in members if m.name == "hello.txt")
    assert hello.size == 3   # "hi\n"
    assert not hello.is_dir
    empty = next(m for m in members if m.name == "empty_dir/")
    assert empty.is_dir


def test_zip_extract_member(sample_zip, tmp_path):
    out_dir = tmp_path / "out"
    target = extract_member(str(sample_zip), "hello.txt", str(out_dir))
    assert Path(target).read_text() == "hi\n"


def test_zip_extract_all(sample_zip, tmp_path):
    out_dir = tmp_path / "out"
    n = extract_all(str(sample_zip), str(out_dir))
    assert n == 2
    assert (out_dir / "hello.txt").read_text() == "hi\n"
    assert (out_dir / "dir" / "inside.txt").read_text() == "deeper\n"


# -- tar listing + extract -------------------------------------------------

@pytest.fixture
def sample_tar(tmp_path):
    p = tmp_path / "sample.tar.gz"
    with tarfile.open(p, "w:gz") as tf:
        for name, body in (("a.txt", b"alpha\n"), ("nested/b.txt", b"beta\n")):
            data = body
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return p


def test_tar_list_members(sample_tar):
    members = list_members(str(sample_tar))
    names = sorted(m.name for m in members)
    assert "a.txt" in names
    assert "nested/b.txt" in names


def test_tar_extract_member(sample_tar, tmp_path):
    out_dir = tmp_path / "x"
    target = extract_member(str(sample_tar), "nested/b.txt", str(out_dir))
    assert Path(target).read_text() == "beta\n"


def test_tar_extract_all(sample_tar, tmp_path):
    out_dir = tmp_path / "x"
    n = extract_all(str(sample_tar), str(out_dir))
    assert n == 2


# -- path-traversal in real archive ---------------------------------------

def test_extract_all_skips_traversal_entries(tmp_path):
    """A ZIP that includes `../evil.txt` should not write outside dest."""
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("../evil.txt", "MALICIOUS\n")
        zf.writestr("safe.txt", "ok\n")
    out_dir = tmp_path / "extract_here"
    n = extract_all(str(p), str(out_dir))
    assert n == 1  # only the safe one
    # Confirm nothing escaped the dest.
    parent_evil = tmp_path / "evil.txt"
    assert not parent_evil.exists()


# -- markdown rendering ---------------------------------------------------

def test_render_listing_markdown(sample_zip):
    md = render_listing_markdown(str(sample_zip))
    assert "# Archive:" in md
    assert "| Name |" in md
    assert "hello.txt" in md


def test_render_listing_markdown_handles_pipe_in_name(tmp_path):
    """Member names containing `|` must be escaped or the markdown table breaks."""
    p = tmp_path / "weird.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("a|b.txt", "x")
    md = render_listing_markdown(str(p))
    assert r"a\|b.txt" in md


# -- file_loader integration ----------------------------------------------

def test_file_loader_routes_archive(sample_zip):
    from src.file_loader import detect_format, load_file
    assert detect_format(sample_zip) == "archive"
    content, encoding, fmt = load_file(str(sample_zip))
    assert fmt == "archive"
    assert "Archive listing" in encoding or encoding == "archive listing"
    assert "hello.txt" in content


def test_file_loader_compound_extension(sample_tar):
    from src.file_loader import detect_format
    assert detect_format(str(sample_tar)) == "archive"
    # Even when given as a plain string
    assert detect_format("foo/bar.tar.gz") == "archive"

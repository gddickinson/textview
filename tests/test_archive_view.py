"""Coverage for src.archive_view — model building, text-preview helper."""
from __future__ import annotations

import io
import zipfile
import tarfile
import pytest
from pathlib import Path

from src.archive_view import _read_member_text, _TEXT_EXTS, _humansize


@pytest.fixture
def sample_zip(tmp_path):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("hello.txt", "hello\nworld\n")
        zf.writestr("dir/inside.py", "print('hi')\n")
        zf.writestr("logo.bin", b"\x00\x01\x02\x03\x04")
    return p


@pytest.fixture
def sample_tar(tmp_path):
    p = tmp_path / "x.tar.gz"
    with tarfile.open(p, "w:gz") as tf:
        data = b"alpha\n"
        info = tarfile.TarInfo("a.txt"); info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return p


def test_read_member_text_zip(sample_zip):
    out = _read_member_text(str(sample_zip), "hello.txt")
    assert out == "hello\nworld\n"


def test_read_member_text_tar(sample_tar):
    out = _read_member_text(str(sample_tar), "a.txt")
    assert out == "alpha\n"


def test_read_member_text_caps_size(tmp_path):
    """Members larger than 1 MB get truncated to the cap."""
    body = b"x" * (1_500_000)
    p = tmp_path / "big.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("big.txt", body)
    out = _read_member_text(str(p), "big.txt")
    assert len(out) <= 1_000_000


def test_text_extensions_set_shape():
    """The text-detection set should contain the obvious ones and
    exclude binary formats."""
    for ext in (".py", ".md", ".json", ".yaml", ".csv", ".txt"):
        assert ext in _TEXT_EXTS
    for ext in (".png", ".pdf", ".zip", ".docx"):
        assert ext not in _TEXT_EXTS


def test_humansize_units():
    assert _humansize(0) == "0 B"
    assert _humansize(500) == "500 B"
    assert _humansize(1024) == "1.0 KB"
    assert _humansize(5 * 1024 * 1024) == "5.0 MB"
    assert _humansize(-1) == "?"


# -- widget-level smoke (use qapp fixture so Qt is initialised) ----------

def test_archive_view_load_builds_tree(qapp, sample_zip):
    from src.archive_view import ArchiveView
    av = ArchiveView()
    ok = av.load(str(sample_zip))
    assert ok
    # Tree model should expose 4 columns.
    model = av.tree.model()
    assert model is not None
    assert model.columnCount() == 4
    # Top-level rows: "hello.txt", "dir", "logo.bin" → 3
    assert model.rowCount() == 3


def test_archive_view_clear(qapp, sample_zip):
    from src.archive_view import ArchiveView
    av = ArchiveView()
    av.load(str(sample_zip))
    av.clear()
    assert av._path is None
    assert av._members == []


def test_archive_view_handles_bad_archive(qapp, tmp_path):
    from src.archive_view import ArchiveView
    p = tmp_path / "bad.zip"
    p.write_bytes(b"not actually a zip file")
    av = ArchiveView()
    ok = av.load(str(p))
    assert ok is False

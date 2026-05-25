"""Coverage for src/blend_inspector.py — magic-byte detection +
header parsing for `.blend` files."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.blend_inspector import (
    BlendInspectError, BlendHeader, is_blend_file, read_header, render_markdown,
)


def _make_blend(path: Path, *,
                 pointer: bytes = b"-",        # 8-byte pointer
                 endian: bytes = b"v",         # little
                 version: bytes = b"404",      # Blender 4.4
                 extra_size: int = 100,
                 ) -> Path:
    """Synthesise a `.blend` file with a valid 12-byte header
    followed by `extra_size` bytes of padding. The padding never
    gets parsed — we only care about the header for inspection."""
    head = b"BLENDER" + pointer + endian + version
    assert len(head) == 12
    path.write_bytes(head + b"\x00" * extra_size)
    return path


# ---------------------------------------------------------- detect --

def test_is_blend_file_true(tmp_path):
    p = _make_blend(tmp_path / "scene.blend")
    assert is_blend_file(p)


def test_is_blend_file_false_text(tmp_path):
    p = tmp_path / "fake.blend"
    p.write_text("not a blender file\n")
    assert not is_blend_file(p)


def test_is_blend_file_missing(tmp_path):
    assert not is_blend_file(tmp_path / "no-such.blend")


def test_is_blend_file_empty(tmp_path):
    p = tmp_path / "empty.blend"
    p.write_bytes(b"")
    assert not is_blend_file(p)


# ---------------------------------------------------------- header --

def test_read_header_4byte_pointer(tmp_path):
    p = _make_blend(tmp_path / "old.blend",
                     pointer=b"_", endian=b"v", version=b"291")
    h = read_header(str(p))
    assert isinstance(h, BlendHeader)
    assert h.pointer_size == 4
    assert h.endianness == "little"
    assert h.version == "2.91"


def test_read_header_8byte_pointer(tmp_path):
    p = _make_blend(tmp_path / "new.blend",
                     pointer=b"-", endian=b"v", version=b"404")
    h = read_header(str(p))
    assert h.pointer_size == 8
    assert h.endianness == "little"
    assert h.version == "4.04"


def test_read_header_big_endian(tmp_path):
    p = _make_blend(tmp_path / "be.blend",
                     pointer=b"-", endian=b"V", version=b"300")
    h = read_header(str(p))
    assert h.endianness == "big"


def test_read_header_too_short_raises(tmp_path):
    p = tmp_path / "tiny.blend"
    p.write_bytes(b"BLENDER")  # only 7 bytes
    with pytest.raises(BlendInspectError):
        read_header(str(p))


def test_read_header_wrong_magic_raises(tmp_path):
    p = tmp_path / "junk.blend"
    p.write_bytes(b"NOTBLEND" + b"\x00" * 20)
    with pytest.raises(BlendInspectError):
        read_header(str(p))


def test_read_header_missing_file_raises(tmp_path):
    with pytest.raises(BlendInspectError):
        read_header(str(tmp_path / "no.blend"))


# ---------------------------------------------------------- render markdown --

def test_render_markdown_includes_header(tmp_path):
    p = _make_blend(tmp_path / "x.blend", version=b"404")
    md = render_markdown(str(p))
    assert "# Blender project: `x.blend`" in md
    assert "Blender version" in md
    assert "4.04" in md
    assert "8 bytes" in md
    assert "little" in md
    # Always points users at the right next step.
    assert "Blender" in md
    assert "stl" in md.lower() or "obj" in md.lower() or "glb" in md.lower()


def test_render_markdown_error_path(tmp_path):
    """Non-blend file → returns a markdown error, not a raise."""
    p = tmp_path / "fake.blend"
    p.write_text("definitely not a blend")
    md = render_markdown(str(p))
    assert "Error" in md


# ---------------------------------------------------------- file_loader integration --

def test_file_loader_routes_blend(tmp_path):
    p = _make_blend(tmp_path / "scene.blend")
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "blend"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "blend"
    assert "Blender" in content
    assert encoding == "blender file"

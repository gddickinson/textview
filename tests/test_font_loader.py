"""Coverage for src.font_loader — extension detection, sample-sheet
shape, malformed-font fallback. Real-font rendering uses a font from
the host's system so the test is platform-tolerant."""
from __future__ import annotations

import shutil
import pytest
from pathlib import Path

from src.font_loader import FONT_EXTENSIONS, is_supported, load_and_render


def test_supported_extensions():
    for ext in (".ttf", ".otf", ".woff", ".woff2", ".ttc"):
        assert is_supported(f"f{ext}")
    assert not is_supported("f.txt")
    assert ".ttf" in FONT_EXTENSIONS


def test_bad_font_data_yields_friendly_html(qapp, tmp_path):
    p = tmp_path / "garbage.ttf"
    p.write_bytes(b"this is not a font")
    html = load_and_render(str(p))
    assert "<h1>" in html
    assert "Could not load" in html or "PyQt6" in html


def _system_font_path() -> str | None:
    """Find a TTF on the host's filesystem so we can exercise the
    happy path. Tries common Mac / Linux / Windows locations."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Geneva.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c
    return None


def test_real_font_renders(qapp):
    p = _system_font_path()
    if p is None:
        pytest.skip("No system font found at any known location.")
    html = load_and_render(p)
    # Sanity: the HTML must include all four key sections.
    assert "Character sets" in html
    assert "Pangram" in html
    assert "Available styles" in html
    assert "Unicode coverage" in html
    # The font family should appear in the H1.
    assert "<h1>" in html
    # font-family declarations should pepper the HTML.
    assert "font-family:" in html


def test_file_loader_routes_font(qapp):
    p = _system_font_path()
    if p is None:
        pytest.skip("No system font found.")
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "font"
    content, encoding, fmt = load_file(p)
    assert fmt == "font"
    assert "font sample" == encoding
    assert "<h1>" in content


def test_html_escaping_in_filename(qapp, tmp_path):
    """A font filename containing HTML metacharacters shouldn't break
    the sample sheet."""
    p = tmp_path / "weird<>name&.ttf"
    p.write_bytes(b"\x00\x01\x02")
    html = load_and_render(str(p))
    assert "<script" not in html
    # The escaped name should be in the report.
    assert "weird&lt;&gt;name&amp;.ttf" in html

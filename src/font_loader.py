"""Font preview for `.ttf` / `.otf` / `.woff` / `.woff2` / `.ttc`.

Loads the file via `QFontDatabase.addApplicationFontFromData`, picks
the first registered family, then builds an HTML sample sheet that
goes through the existing rendered-markdown view. The sample covers:

  - Letters (upper / lower)
  - Digits
  - Common punctuation
  - A pangram at 5 sizes (10pt → 28pt)
  - A weight/style sample line per available style
  - Bonus unicode lines (Greek + Cyrillic + ligature test)

If Qt can't parse the font, the report explains rather than crashing.
"""
from __future__ import annotations

from pathlib import Path


FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc", ".pfb", ".pfa"}


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in FONT_EXTENSIONS


def load_and_render(path: str) -> str:
    """Register the font with `QFontDatabase` and return a self-contained
    HTML sample sheet. The HTML uses `font-family` so the rendered view
    picks up the freshly-loaded font."""
    p = Path(path)
    try:
        from PyQt6.QtGui import QFontDatabase
    except ImportError:
        return _no_qt_message(p)

    data = p.read_bytes()
    font_id = QFontDatabase.addApplicationFontFromData(data)
    if font_id == -1:
        return _bad_font_message(p)
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return _bad_font_message(p)
    family = families[0]
    styles = QFontDatabase.styles(family)
    smooth_sizes = QFontDatabase.smoothSizes(family, styles[0] if styles else "")
    return _render_sample_html(p, family, styles, smooth_sizes)


# ----------------------------------------------------------- internals --

_PANGRAM = "The quick brown fox jumps over the lazy dog."
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"
_PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
_GREEK = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ αβγδεζηθικλμνξοπρστυφχψω"
_CYRILLIC = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
_LIGS = "fi fl ffi ffl Th st ct → ← ↔ ≈ ≠ ≤ ≥ → ☺ ★"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def _render_sample_html(p: Path, family: str, styles: list[str], smooth_sizes: list[int]) -> str:
    f = f"'{family}'"
    sizes = (12, 16, 20, 28, 40)
    style_count = len(styles) if styles else 1
    out: list[str] = []
    out.append(f"<h1>{_esc(family)}</h1>")
    out.append(f"<p><i>File: <code>{_esc(p.name)}</code> · "
               f"{p.stat().st_size:,} bytes · "
               f"{style_count} style{'s' if style_count != 1 else ''} available</i></p>")
    if styles:
        out.append("<p><b>Styles</b>: " + ", ".join(_esc(s) for s in styles) + "</p>")
    out.append("<hr>")

    out.append("<h2>Character sets</h2>")
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_UPPER)}</p>')
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_LOWER)}</p>')
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_DIGITS)}</p>')
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_PUNCT)}</p>')

    out.append("<h2>Pangram at multiple sizes</h2>")
    for s in sizes:
        out.append(
            f'<p style="font-family: {f}; font-size: {s}pt; margin: 0.2em 0;">'
            f'{_esc(_PANGRAM)} <span style="color:#888; font-size: 0.5em;">'
            f'({s}pt)</span></p>'
        )

    # Each style on its own line at 20pt — italic, bold, etc.
    if styles:
        out.append("<h2>Available styles</h2>")
        for style in styles:
            css = _style_css(style)
            out.append(
                f'<p style="font-family: {f}; font-size: 20pt; {css}">'
                f'{_esc(_PANGRAM)} <span style="color:#888; font-size: 0.6em;">'
                f'({_esc(style)})</span></p>'
            )

    out.append("<h2>Unicode coverage</h2>")
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_GREEK)}</p>')
    out.append(f'<p style="font-family: {f}; font-size: 18pt;">{_esc(_CYRILLIC)}</p>')
    out.append('<p style="font-size: 12pt; color: #666;">'
               '(Empty glyphs above mean the font lacks coverage of that range.)</p>')

    out.append("<h2>Ligatures &amp; symbols</h2>")
    out.append(f'<p style="font-family: {f}; font-size: 24pt;">{_esc(_LIGS)}</p>')

    if smooth_sizes:
        out.append("<h2>Recommended sizes</h2>")
        out.append("<p>" + ", ".join(f"{s} pt" for s in smooth_sizes) + "</p>")

    return "\n".join(out) + "\n"


def _style_css(style_name: str) -> str:
    """Translate a Qt style-name string into inline CSS."""
    lower = style_name.lower()
    bits: list[str] = []
    if "italic" in lower or "oblique" in lower:
        bits.append("font-style: italic;")
    if "bold" in lower or "heavy" in lower or "black" in lower:
        bits.append("font-weight: bold;")
    if "thin" in lower or "light" in lower:
        bits.append("font-weight: lighter;")
    return " ".join(bits)


def _no_qt_message(p: Path) -> str:
    return (f"<h1>Font: {_esc(p.name)}</h1>"
            "<p>This viewer requires PyQt6 to render font previews.</p>")


def _bad_font_message(p: Path) -> str:
    return (f"<h1>Font: {_esc(p.name)}</h1>"
            f"<p><b>Could not load font.</b> Qt couldn't parse "
            f"<code>{_esc(p.name)}</code>. The file may be corrupt or in an "
            "unsupported sub-format (e.g. some `.woff2` builds need a "
            "patched Qt).</p>")

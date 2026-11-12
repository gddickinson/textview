"""Themes, Pygments token colours and display defaults for the web viewer.

Themes are `src/themes.py` unchanged. Token colours come from each theme's `pygments_style`, resolved the way
`renderers._build_format_cache` does for the desktop code view. Display defaults are read from the
`DisplaySettings` dataclass in `src/settings.py` (parsed, not imported, because that module needs PyQt6).
"""
from __future__ import annotations

import ast
from pathlib import Path

from pygments.styles import get_style_by_name
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound

from ..themes import THEMES

SETTINGS_PY = Path(__file__).resolve().parents[1] / "settings.py"
WEB_SETTINGS = ["font_family", "font_size", "font_weight", "line_height", "letter_spacing", "word_wrap",
                "show_line_numbers", "tab_width", "padding", "theme", "syntax_highlight", "render_markdown",
                "show_whitespace", "highlight_current_line"]


def display_defaults() -> dict:
    """Literal defaults of the DisplaySettings fields the web viewer mirrors."""
    tree = ast.parse(SETTINGS_PY.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DisplaySettings")
    out = {}
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            try:
                out[node.target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return {k: out[k] for k in WEB_SETTINGS if k in out}


def token_styles(style_name: str) -> dict:
    """short token class -> {c: colour, bg, b: bold, i: italic}, only for classes with a visible style."""
    try:
        style = get_style_by_name(style_name)
    except ClassNotFound:
        style = get_style_by_name("default")
    out = {}
    for tok, short in STANDARD_TYPES.items():
        s = style.style_for_token(tok)
        d = {}
        if s["color"]:
            d["c"] = "#" + s["color"]
        if s["bgcolor"]:
            d["bg"] = "#" + s["bgcolor"]
        if s["bold"]:
            d["b"] = 1
        if s["italic"]:
            d["i"] = 1
        if d:
            out[short] = d
    return out


def themes_payload() -> dict:
    themes = []
    for name, th in THEMES.items():
        themes.append({"name": name, "slug": name.lower().replace(" ", "-"), **th,
                       "tokens": token_styles(th.get("pygments_style", "default"))})
    return {"themes": themes, "defaults": display_defaults()}

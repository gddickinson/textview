"""Format renderers: Pygments-driven syntax highlighting for the code view,
markdown → HTML for the rendered view.
"""
from pygments import lex
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound
from PyQt6.QtGui import (
    QTextCharFormat, QTextCursor, QColor, QFont,
)
# Pure (Qt-free) rendering lives in html_render; re-exported here so existing
# `from .renderers import render_markdown_html` callers keep working.
from .html_render import (  # noqa: F401
    _resolve_lexer, render_markdown_html, render_docx_html, escape_to_html,
)


def _build_format_cache(style):
    """Map every Pygments token in `style` to a QTextCharFormat."""
    cache = {}
    for token, _props in style:
        s = style.style_for_token(token)
        f = QTextCharFormat()
        if s["color"]:
            f.setForeground(QColor(f"#{s['color']}"))
        if s["bgcolor"]:
            f.setBackground(QColor(f"#{s['bgcolor']}"))
        if s["bold"]:
            f.setFontWeight(QFont.Weight.Bold)
        if s["italic"]:
            f.setFontItalic(True)
        if s["underline"]:
            f.setFontUnderline(True)
        cache[token] = f
    return cache


def apply_pygments(plain_edit, content, path=None, style_name="default", format_hint=None):
    """Color the document of a QPlainTextEdit using Pygments tokens.

    Walks the lexer output and applies the appropriate QTextCharFormat to
    each character range. Bails silently on errors so a broken lexer never
    crashes the viewer.
    """
    try:
        style = get_style_by_name(style_name)
    except ClassNotFound:
        style = get_style_by_name("default")

    lexer = _resolve_lexer(content, path, format_hint)
    fmt_cache = _build_format_cache(style)

    doc = plain_edit.document()
    # Re-colouring is not a content edit: keep the document's modified
    # flag as it was, or a freshly opened file reads as "unsaved changes".
    was_modified = doc.isModified()
    cursor = QTextCursor(doc)
    cursor.beginEditBlock()
    pos = 0
    try:
        for token, text in lex(content, lexer):
            length = len(text)
            if length == 0:
                continue
            fmt = fmt_cache.get(token)
            if fmt is None:
                t = token
                while getattr(t, "parent", None) and t not in fmt_cache:
                    t = t.parent
                fmt = fmt_cache.get(t)
            if fmt is not None:
                cursor.setPosition(pos)
                cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
            pos += length
    finally:
        cursor.endEditBlock()
        doc.setModified(was_modified)

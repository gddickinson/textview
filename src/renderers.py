"""Format renderers: Pygments-driven syntax highlighting for the code view,
markdown → HTML for the rendered view.
"""
import html
from pygments import lex
from pygments.lexers import (
    get_lexer_by_name, guess_lexer_for_filename, guess_lexer, TextLexer,
)
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound
from PyQt6.QtGui import (
    QTextCharFormat, QTextCursor, QColor, QFont,
)
import markdown as md_lib


def _resolve_lexer(content, path=None, format_hint=None):
    """Pick the best lexer using whatever info we have.

    Catches `Exception` rather than just `ClassNotFound` because Pygments'
    plugin discovery (entry-point loading) can raise arbitrary ImportErrors
    from third-party packages — e.g. a broken IPython/sqlite3 install. We
    never want a viewer crash because of someone else's plugin.
    """
    if format_hint and format_hint not in ("plain", "code"):
        try:
            return get_lexer_by_name(format_hint)
        except Exception:
            pass
    if path:
        try:
            return guess_lexer_for_filename(path, content)
        except Exception:
            pass
    try:
        return guess_lexer(content)
    except Exception:
        return TextLexer()


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


def render_markdown_html(content, theme, display=None):
    """Render markdown to a styled HTML document tuned to the active theme.

    `display` is the live `DisplaySettings`; when given, font/padding/line-
    height/letter-spacing flow into the inline CSS so the rendered view
    picks up the user's typography settings, not just the theme colors.
    """
    body = md_lib.markdown(
        content,
        extensions=[
            "extra", "tables", "fenced_code",
            "sane_lists", "toc", "codehilite", "admonition",
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "noclasses": True,
                           "pygments_style": theme.get("pygments_style", "default")},
        },
    )
    family = (display.font_family if display else "-apple-system")
    fsize = f"{display.font_size}pt" if display else "inherit"
    lh = (display.line_height if display else 1.65)
    pad = (display.padding if display else 28)
    ls = (f"{display.letter_spacing}px" if display else "normal")
    style = f"""
    <style>
    body {{
        background: {theme['bg']};
        color: {theme['fg']};
        font-family: "{family}", -apple-system, system-ui, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: {fsize};
        line-height: {lh};
        letter-spacing: {ls};
        padding: {pad}px {max(pad, 24)}px;
        max-width: 980px;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {theme['fg']};
        margin-top: 1.4em;
        margin-bottom: 0.6em;
        line-height: 1.25;
    }}
    h1 {{ border-bottom: 1px solid {theme['line_number_fg']}; padding-bottom: 0.2em; }}
    h2 {{ border-bottom: 1px solid {theme['line_number_fg']}; padding-bottom: 0.2em; }}
    p {{ margin: 0.6em 0; }}
    a {{ color: {theme['accent']}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
        background: {theme['current_line']};
        padding: 2px 6px;
        border-radius: 4px;
        font-family: Menlo, Consolas, "Liberation Mono", monospace;
        font-size: 0.95em;
    }}
    pre {{
        background: {theme['current_line']};
        padding: 14px 16px;
        border-radius: 8px;
        overflow-x: auto;
        line-height: 1.45;
    }}
    pre code {{ background: transparent; padding: 0; }}
    blockquote {{
        border-left: 4px solid {theme['accent']};
        margin: 0;
        padding: 6px 16px;
        color: {theme['line_number_fg']};
        background: {theme['current_line']};
        border-radius: 0 6px 6px 0;
    }}
    table {{ border-collapse: collapse; margin: 1em 0; }}
    th, td {{
        border: 1px solid {theme['line_number_fg']};
        padding: 8px 14px;
    }}
    th {{ background: {theme['current_line']}; }}
    hr {{
        border: 0;
        border-top: 1px solid {theme['line_number_fg']};
        margin: 1.4em 0;
    }}
    img {{ max-width: 100%; }}
    ul, ol {{ padding-left: 1.6em; }}
    </style>
    """
    return f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>{body}</body></html>"


def render_docx_html(body_html, theme, display=None):
    """Wrap a DOCX-rendered HTML fragment (from mammoth) in a themed page.

    `display` is the live `DisplaySettings`; when given, font / padding /
    line-height flow into the wrapper CSS so the rendered Word document
    picks up typography settings as well as theme colors.
    """
    family = (display.font_family if display else "-apple-system")
    fsize = f"{display.font_size}pt" if display else "inherit"
    lh = (display.line_height if display else 1.6)
    pad = (display.padding if display else 28)
    ls = (f"{display.letter_spacing}px" if display else "normal")
    style = f"""
    <style>
    body {{
        background: {theme['bg']};
        color: {theme['fg']};
        font-family: "{family}", -apple-system, system-ui, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: {fsize};
        line-height: {lh};
        letter-spacing: {ls};
        padding: {pad}px {max(pad, 24)}px;
        max-width: 980px;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {theme['fg']};
        margin-top: 1.4em; margin-bottom: 0.6em; line-height: 1.25;
    }}
    h1 {{ border-bottom: 1px solid {theme['line_number_fg']}; padding-bottom: 0.2em; }}
    h2 {{ border-bottom: 1px solid {theme['line_number_fg']}; padding-bottom: 0.2em; }}
    p {{ margin: 0.6em 0; }}
    a {{ color: {theme['accent']}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code, pre {{
        background: {theme['current_line']};
        font-family: Menlo, Consolas, "Liberation Mono", monospace;
        border-radius: 4px;
    }}
    code {{ padding: 2px 6px; font-size: 0.95em; }}
    pre {{ padding: 14px 16px; overflow-x: auto; }}
    blockquote {{
        border-left: 4px solid {theme['accent']};
        margin: 0; padding: 6px 16px;
        color: {theme['line_number_fg']};
        background: {theme['current_line']};
        border-radius: 0 6px 6px 0;
    }}
    table {{ border-collapse: collapse; margin: 1em 0; }}
    th, td {{ border: 1px solid {theme['line_number_fg']}; padding: 8px 14px; }}
    th {{ background: {theme['current_line']}; }}
    hr {{ border: 0; border-top: 1px solid {theme['line_number_fg']}; margin: 1.4em 0; }}
    img {{ max-width: 100%; }}
    ul, ol {{ padding-left: 1.6em; }}
    </style>
    """
    return f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>{body_html}</body></html>"


def escape_to_html(text, theme):
    """Wrap plain text in a themed HTML <pre> for export-as-html on non-markdown."""
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>"
        f"body {{ background:{theme['bg']}; color:{theme['fg']}; "
        f"font-family: Menlo, Consolas, monospace; padding:24px; }} "
        f"pre {{ white-space: pre-wrap; word-wrap: break-word; }}"
        f"</style></head><body><pre>{html.escape(text)}</pre></body></html>"
    )

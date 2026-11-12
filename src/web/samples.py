"""Demo files for the web viewer and the payload the viewer page renders.

Every payload is built with TextView's own loaders: `file_loader.load_file` (format detection, encoding probing,
document / spreadsheet / archive extraction), `html_render` (Pygments lexer choice, themed markdown and DOCX HTML),
`table_data.parse_delimited` (the table view's CSV parsing) and `templates` (File -> New from template).

Items: the repo's sample_files/, the extra demo files in src/web/samples/ (made by scripts/make_web_samples.py with
TextView's Save As converters) and the ~25 starter templates. Ids are file names, or "tpl-<template id>".
"""
from __future__ import annotations

import json
from pathlib import Path

from pygments import lex
from pygments.token import STANDARD_TYPES

from ..file_loader import (DOCUMENT_FORMATS, IMAGE_FORMATS, MEDIA_FORMATS, TABLE_FORMATS, detect_format,
                           humansize, load_file)
from ..html_render import _resolve_lexer, render_docx_html, render_markdown_html
from ..table_data import detect_numeric_columns, parse_delimited
from ..templates import list_templates
from ..themes import THEMES

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIRS = [ROOT / "sample_files", Path(__file__).resolve().parent / "samples"]
MAX_TEXT = 200_000        # characters of text sent to the browser
MAX_TOKENS_TEXT = 60_000  # longer files are shown without syntax colours
RENDERED_FORMATS = {"markdown", "docx", "archive"}


def sample_files() -> dict[str, Path]:
    out = {}
    for d in SAMPLE_DIRS:
        for p in sorted(d.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                out[p.name] = p
    return out


def templates() -> dict:
    return {f"tpl-{t.id}": t for t in list_templates()}


def view_kind(fmt: str) -> str:
    """Which viewer the desktop app would use (TextViewer modes)."""
    if fmt in IMAGE_FORMATS:
        return "image"
    if fmt in MEDIA_FORMATS:
        return "media"
    if fmt in TABLE_FORMATS:
        return "table"
    if fmt == "pdf":
        return "pdf"
    if fmt == "notebook":
        return "notebook"
    if fmt in RENDERED_FORMATS or fmt in DOCUMENT_FORMATS:
        return "rendered"
    return "code"


def slug(theme: str) -> str:
    return theme.lower().replace(" ", "-")


def theme_by_slug(s: str) -> str | None:
    return next((t for t in THEMES if slug(t) == s), None)


def catalog() -> list[dict]:
    """The viewer's file list."""
    items = []
    for name, p in sample_files().items():
        fmt = detect_format(p)
        items.append({"id": name, "name": name, "group": "Sample files" if p.parent.name == "sample_files"
                      else "Made by Save As", "format": fmt, "view": view_kind(fmt), "size": p.stat().st_size,
                      "size_h": humansize(p.stat().st_size)})
    for tid, t in templates().items():
        view = "code" if view_kind(t.format) == "notebook" else view_kind(t.format)
        items.append({"id": tid, "name": t.name, "group": f"Template · {t.category}", "format": t.format,
                      "view": view, "size": len(t.body.encode()), "size_h": humansize(len(t.body.encode())),
                      "description": t.description, "extension": t.extension})
    return items


def _short(tok) -> str:
    """Pygments short class name, walking up to the nearest standard parent (as apply_pygments does)."""
    while tok not in STANDARD_TYPES and tok.parent is not None:
        tok = tok.parent
    return STANDARD_TYPES.get(tok, "")


def tokens(text: str, path: str | None, fmt: str) -> tuple[list, str]:
    """[[class, text], ...] with adjacent equal classes merged, plus the lexer name."""
    lexer = _resolve_lexer(text, path, fmt)
    out: list[list[str]] = []
    for tok, val in lex(text, lexer):
        c = _short(tok)
        if out and out[-1][0] == c:
            out[-1][1] += val
        else:
            out.append([c, val])
    return out, lexer.name


def _code_part(text: str, path: str | None, fmt: str) -> dict:
    d = {"text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT, "lines": text.count("\n") + 1}
    if len(text) <= MAX_TOKENS_TEXT:
        d["tokens"], d["lexer"] = tokens(text[:MAX_TEXT], path, fmt)
    return d


def _table_part(text: str) -> dict:
    header, rows, delim = parse_delimited(text)
    return {"header": header, "rows": rows, "delimiter": delim, "numeric": detect_numeric_columns(header, rows)}


def _notebook_part(path: Path) -> dict:
    nb = json.loads(path.read_text(encoding="utf-8"))
    lang = (nb.get("metadata", {}).get("kernelspec", {}) or {}).get("language", "python")
    cells = []
    for c in nb.get("cells", []):
        src = "".join(c.get("source", []))
        cell = {"type": c.get("cell_type"), "source": src, "count": c.get("execution_count")}
        if c.get("cell_type") == "markdown":
            import markdown as md_lib
            cell["html"] = md_lib.markdown(src, extensions=["extra", "sane_lists"])
        if c.get("cell_type") == "code":
            cell["tokens"], _ = tokens(src, None, lang)
            outs = []
            for o in c.get("outputs", []):
                data = o.get("data", {})
                if o.get("output_type") == "stream":
                    outs.append({"kind": "text", "text": "".join(o.get("text", []))})
                elif o.get("output_type") == "error":
                    outs.append({"kind": "text", "text": f"{o.get('ename')}: {o.get('evalue')}"})
                elif "image/png" in data:
                    outs.append({"kind": "png", "data": "".join(data["image/png"]).replace("\n", "")})
                elif "text/plain" in data:
                    outs.append({"kind": "text", "text": "".join(data["text/plain"])})
            cell["outputs"] = outs
        cells.append(cell)
    return {"cells": cells, "language": lang}


def _image_part(path: Path) -> dict:
    from PIL import Image
    with Image.open(path) as im:
        return {"width": im.width, "height": im.height, "mode": im.mode,
                "frames": getattr(im, "n_frames", 1), "image_format": im.format}


def payload_for_path(path: Path, display_name: str | None = None) -> dict:
    """Everything the viewer page needs for one file on disk."""
    name = display_name or path.name
    content, encoding, fmt = load_file(str(path))
    view = view_kind(fmt)
    d = {"name": name, "format": fmt, "view": view, "encoding": encoding, "size": path.stat().st_size,
         "size_h": humansize(path.stat().st_size), "rendered": fmt in RENDERED_FORMATS}
    if view == "image":
        d["image"] = _image_part(path)
    elif view == "table":
        d["table"] = _table_part(content)
        d.update(_code_part(content, None, "text"))
        d.pop("tokens", None)
        d.pop("lexer", None)
    elif view == "notebook":
        d["notebook"] = _notebook_part(path)
    elif view in ("pdf", "rendered"):
        d.update(_code_part(content, None, "text" if fmt in DOCUMENT_FORMATS else "markdown" if fmt == "archive" else fmt))
    elif view == "code":
        d.update(_code_part(content, name, fmt))
    return d


def payload(item_id: str) -> dict | None:
    files = sample_files()
    if item_id in files:
        d = payload_for_path(files[item_id])
        d["id"] = item_id
        d["raw"] = f"api/raw/{item_id}"
        return d
    t = templates().get(item_id)
    if t is None:
        return None
    fname = t.extension if not t.extension.startswith(".") else f"untitled{t.extension}"
    d = {"id": item_id, "name": fname, "title": t.name, "format": t.format, "view": view_kind(t.format),
         "encoding": "utf-8", "size": len(t.body.encode()), "size_h": humansize(len(t.body.encode())),
         "description": t.description, "rendered": t.format == "markdown"}
    if d["view"] == "notebook":
        d["view"] = "code"
    if d["view"] == "table":
        d["table"] = _table_part(t.body)
    d.update(_code_part(t.body, fname, t.format))
    return d


def rendered_html_for_path(p: Path, theme: str) -> str | None:
    """Themed HTML for the rendered view (markdown, DOCX, archive listing), exactly as the desktop app builds it."""
    th = THEMES[theme]
    fmt = detect_format(p)
    if fmt == "docx":
        from ..document_extract import extract_docx_html
        return render_docx_html(extract_docx_html(str(p)), th)
    if fmt in ("markdown", "archive"):
        return render_markdown_html(load_file(str(p))[0], th)
    return None


def rendered_html(item_id: str, theme: str) -> str | None:
    files = sample_files()
    if item_id in files:
        return rendered_html_for_path(files[item_id], theme)
    t = templates().get(item_id)
    if t is not None and t.format == "markdown":
        return render_markdown_html(t.body, THEMES[theme])
    return None


def rendered_ids() -> list[str]:
    ids = [n for n, p in sample_files().items() if detect_format(p) in RENDERED_FORMATS]
    return ids + [i for i, t in templates().items() if t.format == "markdown"]

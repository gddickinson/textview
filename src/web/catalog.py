"""Format catalogue, file-format database and documentation pages for the web interface.

- `formats_payload()` — the extension / filename -> format maps from `file_loader` (what the desktop app opens and in
  which viewer), grouped by format id.
- `format_db_payload()` — the bundled `data/file_formats.json` through `format_db.FormatEntry`; a user's own
  `~/.config/TextView/file_formats.json` is deliberately NOT merged, so nothing personal reaches the static site.
- `docs_index()` / `doc_page(name)` — the repo's `docs/*.md` rendered with the same Python-Markdown extensions the
  desktop viewer uses; links between docs become in-app routes.
- `why_payload()` — the "Why TextView" bullets from README.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import markdown as md_lib

from .. import format_db
from ..file_loader import FILENAME_MAP, FORMAT_MAP
from .samples import view_kind

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
MD_EXT = ["extra", "tables", "fenced_code", "sane_lists", "toc", "admonition"]

# Order and labels for the docs reader (stems of docs/*.md). INDEX is the docs home page.
DOC_GROUPS = [
    ("Start", ["INDEX", "overview", "file-formats", "shortcuts", "troubleshooting"]),
    ("AI features", ["workspace-rag", "chat", "unknown-files", "file-formats-db", "agent-api"]),
    ("Safety", ["security"]),
    ("Extending", ["scripts", "plugins", "hooks", "control-server", "lsp", "notebook", "architecture"]),
]


def formats_payload() -> dict:
    groups: dict[str, dict] = {}
    for ext, fmt in FORMAT_MAP.items():
        g = groups.setdefault(fmt, {"format": fmt, "view": view_kind(fmt), "extensions": [], "filenames": []})
        g["extensions"].append(ext)
    for name, fmt in FILENAME_MAP.items():
        g = groups.setdefault(fmt, {"format": fmt, "view": view_kind(fmt), "extensions": [], "filenames": []})
        g["filenames"].append(name)
    rows = sorted(groups.values(), key=lambda g: (g["view"], g["format"]))
    return {"n_extensions": len(FORMAT_MAP), "n_filenames": len(FILENAME_MAP), "n_formats": len(groups),
            "format_map": FORMAT_MAP, "filename_map": FILENAME_MAP, "groups": rows}


def bundled_entries() -> list:
    raw = format_db._read(format_db._BUNDLED) or {}
    return [format_db.FormatEntry.from_dict(r) for r in raw.get("formats", []) if r.get("id")]


def format_db_payload() -> dict:
    entries = bundled_entries()
    cats: dict[str, int] = {}
    for e in entries:
        cats[e.category] = cats.get(e.category, 0) + 1
    return {"entries": [{**e.__dict__, "html": md_lib.markdown(e.to_markdown(), extensions=MD_EXT)} for e in entries],
            "categories": dict(sorted(cats.items(), key=lambda x: (-x[1], x[0])))}


def _title(text: str, stem: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else stem


def docs_index() -> dict:
    groups = []
    for label, stems in DOC_GROUPS:
        items = [{"name": s, "title": _title((DOCS / f"{s}.md").read_text(encoding="utf-8"), s)}
                 for s in stems if (DOCS / f"{s}.md").exists()]
        groups.append({"label": label, "docs": items})
    return {"groups": groups}


def doc_names() -> list[str]:
    return [s for _, stems in DOC_GROUPS for s in stems if (DOCS / f"{s}.md").exists()]


def _fix_links(html: str) -> str:
    """docs/x.md links -> #/docs/x; repo files -> GitHub; screenshots -> api/shot/<name>."""
    def href(m):
        url = m.group(1)
        if re.match(r"^[a-z]+:", url) or url.startswith("#"):
            return m.group(0)
        base, _, frag = url.partition("#")
        stem = Path(base).stem
        if base.endswith(".md") and (DOCS / f"{stem}.md").exists():
            return f'href="#/docs/{stem}"'
        clean = base.lstrip("./")
        while clean.startswith("../"):
            clean = clean[3:]
        return f'href="https://github.com/gddickinson/textview/blob/main/{clean}"'
    html = re.sub(r'href="([^"]+)"', href, html)
    return re.sub(r'src="(?:\.\./)?(?:docs/)?screenshots/([\w.-]+\.png)"', r'src="api/shot/\1"', html)


def doc_page(name: str) -> dict | None:
    if name not in doc_names():
        return None
    text = (DOCS / f"{name}.md").read_text(encoding="utf-8")
    return {"name": name, "title": _title(text, name), "html": _fix_links(md_lib.markdown(text, extensions=MD_EXT))}


def screenshots() -> dict[str, Path]:
    return {p.name: p for p in sorted((DOCS / "screenshots").glob("*.png"))}


def why_payload() -> dict:
    """README "Why TextView" bullets as HTML list items (title + body)."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = text.split("## Why TextView", 1)[1].split("\n## ", 1)[0]
    items = []
    for block in re.split(r"\n- ", "\n" + sec.strip())[1:]:
        block = " ".join(block.split())
        m = re.match(r"\*\*(.+?)\*\*\s*(.*)", block)
        if m:
            body = re.sub(r"→\s*\[`[^`]+`\]\([^)]+\)", "", m.group(2)).strip()
            items.append({"title": m.group(1).rstrip(".:"), "html": _fix_links(md_lib.markdown(body))})
    shots = [{"file": n, "caption": c} for n, c in re.findall(r"!\[([^\]]*)\]\(docs/screenshots/([\w.-]+)\)", text)]
    return {"items": items, "shots": [{"file": s["caption"], "alt": s["file"]} for s in shots]}

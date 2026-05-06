"""LLM tools that expose the in-repo `docs/` folder so chat agents can
look up authoritative information about the app instead of guessing
from training priors.

The same files back the user-facing Help menu — single source of truth.
"""
from __future__ import annotations
from pathlib import Path

from .tools_base import Tool


def _docs_dir() -> Path:
    """Project-relative `docs/` (we sit at `src/llm/`)."""
    return Path(__file__).resolve().parents[2] / "docs"


def _read_index_summary() -> dict[str, str]:
    """Map each `<name>.md` in docs/ to its first non-empty heading or
    paragraph (used as the one-line description in `list_docs`)."""
    out: dict[str, str] = {}
    for p in sorted(_docs_dir().glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        # First "# Heading" or first non-blank paragraph.
        first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
        if first_line.startswith("# "):
            out[p.stem] = first_line[2:].strip()
        else:
            out[p.stem] = first_line[:80]
    return out


def _list_docs(window) -> str:
    summary = _read_index_summary()
    if not summary: return "(no docs found)"
    width = max(len(n) for n in summary)
    return "\n".join(f"  {name:<{width}}  — {desc}" for name, desc in summary.items())


def _read_doc(window, name: str = "") -> str:
    name = (name or "").strip()
    if not name: return "ERROR: provide `name` (e.g. 'INDEX', 'file-formats')."
    if name.endswith(".md"): name = name[:-3]
    p = _docs_dir() / f"{name}.md"
    if not p.is_file():
        avail = ", ".join(sorted(d.stem for d in _docs_dir().glob("*.md")))
        return f"ERROR: no doc {name!r}. Available: {avail}"
    return p.read_text(encoding="utf-8")


def _search_docs(window, query: str = "") -> str:
    query = (query or "").strip()
    if not query: return "ERROR: provide `query`."
    q_lc = query.lower()
    out: list[str] = []
    for p in sorted(_docs_dir().glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if q_lc in line.lower():
                snippet = line.strip()[:140]
                out.append(f"{p.stem}:{i}: {snippet}")
                if len(out) >= 50:
                    out.append(f"... (cap reached at 50 hits)")
                    return "\n".join(out)
    return "\n".join(out) if out else f"(no matches for {query!r})"


DOC_TOOLS: list[Tool] = [
    Tool(name="list_docs",
         description="List every documentation page bundled with the app, "
                     "with a one-line description. Call this first when the "
                     "user asks about features, capabilities, or how to use "
                     "something.",
         input_schema={"type": "object", "properties": {}, "required": []},
         call=_list_docs),
    Tool(name="read_doc",
         description="Return the full markdown of a documentation page. "
                     "`name` is the file stem (e.g. 'INDEX', 'file-formats', "
                     "'agent-api', 'notebook', 'lsp'). Always read INDEX "
                     "first if you don't know what's available.",
         input_schema={"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]},
         call=_read_doc),
    Tool(name="search_docs",
         description="Keyword search across all documentation pages. Returns "
                     "matching `<doc>:<line>: <snippet>` triples. Use this "
                     "to locate a specific feature when you don't know which "
                     "page describes it.",
         input_schema={"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]},
         call=_search_docs),
]

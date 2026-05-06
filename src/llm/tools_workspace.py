"""LLM tools for workspace-wide RAG.

Two read-only tools:
    index_workspace(root?)  — build/refresh the index
    query_workspace(query)  — ranked snippets with file+locator citations

Side effect: when called from a chat with a citation panel attached,
results are pushed to the panel so the user can click any citation
to open the file at the right line/page/cell. That's the "agent
shows you the files" loop.
"""
from __future__ import annotations
from pathlib import Path

from .tools_base import Tool
from ..workspace_index import get_or_build_index, walk_workspace_files


def _project_root(window) -> Path | None:
    """Same heuristic as workspace_search._index_root."""
    pp = getattr(window, "project_panel", None)
    if pp is not None:
        try:
            root = pp._model.rootPath() if pp._model else ""
            if root and Path(root).is_dir():
                return Path(root)
        except Exception:
            pass
    cur = getattr(window, "_current_path", None)
    if cur:
        p = Path(cur).parent
        if p.is_dir(): return p
    return None


def _index_workspace(window, root: str | None = None, force: bool = False) -> str:
    if root:
        root_path = Path(root).expanduser().resolve()
        if not root_path.is_dir():
            return f"ERROR: not a directory: {root_path}"
    else:
        root_path = _project_root(window)
        if root_path is None:
            return ("ERROR: no project root. Open a folder via "
                    "File → Open folder, or pass `root`.")
    from ..busy_indicator import BusyIndicator
    with BusyIndicator(window, f"Indexing {root_path.name}…"):
        idx = get_or_build_index(root_path, force=bool(force))
    s = idx.stats()
    return (f"Indexed {s['n_chunks']} chunks under {s['root']}\n"
            f"  by kind: {s['by_kind']}")


def _query_workspace(window, query: str, k: int = 8,
                     root: str | None = None) -> str:
    if not query or not query.strip():
        return "ERROR: provide `query`"
    root_path = (Path(root).expanduser().resolve() if root
                 else _project_root(window))
    if root_path is None or not root_path.is_dir():
        return "ERROR: no project root. Pass `root` or open a folder."
    from ..busy_indicator import BusyIndicator
    with BusyIndicator(window, f"Searching workspace for {query!r}…"):
        idx = get_or_build_index(root_path)
        if not idx.chunks:
            return "(empty index — does the folder contain indexable files?)"
        results = idx.search(query, k=int(k))
    if not results:
        return f"(no matches for {query!r})"
    # Side effect: push to citation panel (so the user can click through).
    panel = getattr(window, "citation_panel", None)
    if panel is not None:
        try: panel.set_citations([c for _, c in results], query=query)
        except Exception: pass
    out = [f"{len(results)} match(es) for {query!r}:"]
    for score, ch in results:
        try: rel = str(Path(ch.path).relative_to(root_path))
        except ValueError: rel = ch.path
        loc = ch.locator or "(file)"
        snippet = " ".join(ch.text.split())[:180]
        out.append(f"  [{score:.2f}] {rel}  {loc}\n      {snippet}")
    out.append("\nClick any citation in the Citations panel to open it.")
    return "\n".join(out)


def _list_workspace(window, root: str | None = None) -> str:
    """Quick directory inventory — what file kinds live here?"""
    root_path = (Path(root).expanduser().resolve() if root
                 else _project_root(window))
    if root_path is None: return "ERROR: no project root."
    counts: dict[str, int] = {}
    total = 0
    for p in walk_workspace_files(root_path):
        ext = p.suffix.lower() or "(no-ext)"
        counts[ext] = counts.get(ext, 0) + 1
        total += 1
    if not counts: return f"(no indexable files under {root_path})"
    rows = [f"{ext:>10}  {n}" for ext, n in sorted(counts.items(), key=lambda x: -x[1])]
    return f"{total} files under {root_path}:\n" + "\n".join(rows)


WORKSPACE_TOOLS: list[Tool] = [
    Tool(name="list_workspace",
         description="Inventory the project root: count of files by extension. "
                     "Cheap; use BEFORE asking the user 'what's in this project'. "
                     "Pass `root` to point at a different folder.",
         input_schema={"type": "object",
                       "properties": {"root": {"type": "string"}},
                       "required": []},
         call=_list_workspace),
    Tool(name="index_workspace",
         description="Build or refresh a lexical search index over every "
                     "indexable file in the project root. Cheap if cache "
                     "is fresh. Pass `force: true` to rebuild from scratch. "
                     "Pass `root` to index a different folder.",
         input_schema={"type": "object",
                       "properties": {
                           "root": {"type": "string"},
                           "force": {"type": "boolean"},
                       },
                       "required": []},
         call=_index_workspace),
    Tool(name="query_workspace",
         description="Search every text/code/PDF/notebook file in the project "
                     "for `query`. Returns ranked snippets with `(file, "
                     "locator)` citations the user can click open. Use this "
                     "ANY TIME the user asks 'where is X', 'find Y', "
                     "'what's in this project', 'how does Z work', etc. — "
                     "always cite specific files instead of guessing.",
         input_schema={"type": "object",
                       "properties": {
                           "query": {"type": "string"},
                           "k": {"type": "integer",
                                 "description": "max results (default 8)"},
                           "root": {"type": "string"},
                       },
                       "required": ["query"]},
         call=_query_workspace),
]

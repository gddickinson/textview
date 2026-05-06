"""LLM tools for the file-format database.

Read-only:
    lookup_format(name_or_extension)  — return a single entry as JSON
    search_formats(query)             — keyword search across the DB
    list_format_categories()          — overview of categories + counts

Action (chat-panel "Allow actions"):
    add_format_entry(entry)  — append/replace an entry in the user JSON
"""
from __future__ import annotations
import json

from .tools_base import Tool


# ---- read-only ----------------------------------------------------------

def _lookup_format(window, name_or_extension: str) -> str:
    from ..format_db import db
    if not name_or_extension: return "ERROR: provide `name_or_extension`."
    d = db()
    q = name_or_extension.strip()
    # Try several lookup strategies.
    e = d.lookup_by_extension(q) if q.startswith(".") else None
    e = e or d.lookup_by_id(q.lower())
    e = e or d.lookup_by_filename(q)
    e = e or d.lookup_by_extension("." + q.lower())   # bare ext like "pdf"
    if e is None:
        # Fall back to top search hit.
        hits = d.search(q, limit=3)
        if not hits: return f"(no entry for {name_or_extension!r})"
        e = hits[0]
    return json.dumps({
        "id": e.id, "name": e.name, "extensions": e.extensions,
        "filenames": e.filenames, "category": e.category, "binary": e.binary,
        "description": e.description, "magic_bytes": e.magic_bytes,
        "use_cases": e.use_cases, "tools": e.tools,
        "open_with": e.open_with, "convert": e.convert,
        "links": e.links, "tags": e.tags,
    }, indent=2)


def _search_formats(window, query: str, limit: int = 8) -> str:
    from ..format_db import db
    if not query: return "ERROR: provide `query`."
    hits = db().search(query, limit=int(limit))
    if not hits: return f"(no matches for {query!r})"
    out = [f"{len(hits)} match(es) for {query!r}:"]
    for e in hits:
        bits = ", ".join(e.extensions[:4]) or (e.filenames[0] if e.filenames else "")
        out.append(f"  {e.id:14s}  {bits:24s}  {e.name}")
        if e.description:
            out.append(f"      {e.description[:140]}")
    return "\n".join(out)


def _list_format_categories(window) -> str:
    from ..format_db import db
    d = db()
    cats = d.categories()
    return (f"{len(d.entries)} entries across {len(cats)} categories:\n"
            + "\n".join(f"  {cat:14s} {n}" for cat, n in cats.items()))


# ---- action: add an entry to the user JSON -----------------------------

def _add_format_entry(window, entry: dict) -> str:
    """Append or replace an entry in the user file. The user must have
    'Allow actions' enabled in the chat panel — bare-string injection
    can't reach this code path otherwise."""
    from ..format_db import add_user_entry
    if not isinstance(entry, dict):
        return "ERROR: `entry` must be a JSON object with at least an `id`."
    if not entry.get("id"):
        return "ERROR: entry needs an `id` (slug, e.g. 'parquet')."
    if not entry.get("name"):
        return "ERROR: entry needs a `name` (display title)."
    ok, msg = add_user_entry(entry)
    return msg if ok else f"ERROR: {msg}"


# ---- registration -----------------------------------------------------

FORMAT_DB_TOOLS_RO: list[Tool] = [
    Tool(name="lookup_format",
         description="Look up a single file format in the bundled database. "
                     "Pass an extension ('.parquet', 'pdf'), an id "
                     "('parquet'), or a filename ('Dockerfile'). Returns "
                     "structured info: description, common uses, tools, how "
                     "to open / inspect / convert it. Use this first when "
                     "the user asks 'what is this file?' or 'how do I open "
                     "X' — beats general knowledge because it stays in sync "
                     "with what TextView actually supports.",
         input_schema={"type": "object",
                       "properties": {"name_or_extension": {"type": "string"}},
                       "required": ["name_or_extension"]},
         call=_lookup_format),
    Tool(name="search_formats",
         description="Keyword search across the file-format database. "
                     "Returns a ranked list of matches with one-line "
                     "summaries. Use when the user describes a format "
                     "vaguely (e.g. 'compressed columnar', 'lossless audio').",
         input_schema={"type": "object",
                       "properties": {
                           "query": {"type": "string"},
                           "limit": {"type": "integer"},
                       },
                       "required": ["query"]},
         call=_search_formats),
    Tool(name="list_format_categories",
         description="Overview of how the database is organised: each "
                     "category and the number of entries it contains.",
         input_schema={"type": "object", "properties": {}, "required": []},
         call=_list_format_categories),
]


FORMAT_DB_TOOLS_ACTION: list[Tool] = [
    Tool(name="add_format_entry",
         description="Append or replace a file-format entry in the user "
                     "JSON (`~/.config/TextView/file_formats.json`). The "
                     "entry must include `id` (slug) and `name`; extensions, "
                     "category, description, tools, etc. are optional. Use "
                     "this when the user asks the agent to remember a new "
                     "format or correct an existing one.",
         input_schema={"type": "object",
                       "properties": {
                           "entry": {"type": "object",
                                     "description": "Format entry shape — "
                                     "see data/file_formats.json for examples."},
                       },
                       "required": ["entry"]},
         call=_add_format_entry, destructive=True),
]

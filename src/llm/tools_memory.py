"""LLM tools for the memory system.

Read-only:  `memory_list`, `memory_recall`, `memory_index`.
Destructive: `memory_save`, `memory_update`, `memory_delete`.

Every operation goes through `MemoryStore`, which restricts names to
`[a-z0-9_-]{1,64}` so no LLM-supplied path can escape the directory.
"""
from .tools_base import Tool
from ..memory import (
    MemoryStore, Memory, VALID_TYPES, VALID_IMPORTANCE, slugify,
)


def _store():
    return MemoryStore()


def _list(window, type: str | None = None,
          importance: str | None = None):
    mems = _store().list(type=type, importance=importance)
    if not mems:
        return "(no memories saved)"
    out = [f"{len(mems)} memor{'y' if len(mems) == 1 else 'ies'}:"]
    for m in mems:
        star = " ⭐" if m.importance == "high" else ""
        desc = m.description or "(no description)"
        out.append(f"  [{m.type:<10}] {m.name}{star} — {desc}")
    return "\n".join(out)


def _recall(window, query: str, limit: int = 5):
    mems = _store().search(query)[:int(limit)]
    if not mems:
        return f"(no memories match {query!r})"
    out = [f"{len(mems)} match(es) for {query!r}:"]
    for m in mems:
        out.append(
            f"\n══ {m.name} ({m.type}, importance={m.importance}) ══\n"
            f"{m.description}\n\n{m.content[:1000]}"
            + ("\n…[truncated]" if len(m.content) > 1000 else "")
        )
        # Touch so we know this memory was useful — feeds future
        # importance / compaction decisions.
        _store().touch(m.name)
    return "\n".join(out)


def _index(window):
    """Return the auto-generated `MEMORY.md` index — useful for the
    LLM to scan available memories without loading each body."""
    return _store().index_text()


def _save(window, type: str, description: str, content: str,
          name: str | None = None, importance: str = "medium"):
    if type not in VALID_TYPES:
        return (f"error: invalid type {type!r}. Use one of "
                f"{sorted(VALID_TYPES)}.")
    if importance not in VALID_IMPORTANCE:
        return (f"error: invalid importance {importance!r}. Use "
                f"low / medium / high.")
    name = name or slugify(description)
    s = _store()
    if s.get(name) is not None:
        return (f"error: memory {name!r} already exists. Use "
                f"`memory_update` to modify, or pick a different name.")
    mem = Memory(name=name, type=type, description=description,
                 content=content, importance=importance)
    try:
        s.add(mem)
    except (ValueError, FileExistsError, OSError) as e:
        return f"error: {e}"
    return f"saved {type} memory '{name}' (importance={importance})"


def _update(window, name: str, content: str | None = None,
            description: str | None = None,
            importance: str | None = None):
    try:
        mem = _store().update(name, content=content,
                              description=description,
                              importance=importance)
    except ValueError as e:
        return f"error: {e}"
    if mem is None:
        return f"error: no memory named '{name}'."
    return f"updated '{name}' (last_used refreshed)"


def _delete(window, name: str):
    if _store().delete(name):
        return f"deleted memory '{name}'"
    return f"error: no memory named '{name}' (or invalid name)."


MEMORY_TOOLS_RO: list[Tool] = [
    Tool(
        name="memory_list",
        description="List stored memories. Optionally filter by `type` "
                    "(session / user / project / reference / feedback) "
                    "or `importance` (low / medium / high).",
        input_schema={
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "importance": {"type": "string"},
            },
        },
        call=_list,
    ),
    Tool(
        name="memory_recall",
        description="Search memories by `query` (matches name, "
                    "description, body in that priority). Returns up "
                    "to `limit` (default 5) most relevant entries with "
                    "their full content. Touches each surfaced memory "
                    "so its `last_used` timestamp updates.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        call=_recall,
    ),
    Tool(
        name="memory_index",
        description="Return the auto-generated MEMORY.md index — "
                    "names + descriptions of every memory grouped by "
                    "type. Cheap way to scan what's available.",
        input_schema={"type": "object", "properties": {}},
        call=_index,
    ),
]


MEMORY_TOOLS_ACTION: list[Tool] = [
    Tool(
        name="memory_save",
        description="Save a new memory. `type`: session (recent activity), "
                    "user (preferences/role/expertise), project (decisions/"
                    "deadlines/why), reference (URLs/external systems), "
                    "feedback (corrections to apply going forward). "
                    "`importance`: low / medium / high — high is exempt "
                    "from auto-compaction. `name` defaults to a slug of "
                    "`description` if not given.",
        input_schema={
            "type": "object",
            "properties": {
                "type":        {"type": "string"},
                "description": {"type": "string"},
                "content":     {"type": "string"},
                "name":        {"type": "string"},
                "importance":  {"type": "string", "default": "medium"},
            },
            "required": ["type", "description", "content"],
        },
        call=_save,
        destructive=True,
    ),
    Tool(
        name="memory_update",
        description="Modify an existing memory. Pass any of `content`, "
                    "`description`, or `importance` (others stay).",
        input_schema={
            "type": "object",
            "properties": {
                "name":        {"type": "string"},
                "content":     {"type": "string"},
                "description": {"type": "string"},
                "importance":  {"type": "string"},
            },
            "required": ["name"],
        },
        call=_update,
        destructive=True,
    ),
    Tool(
        name="memory_delete",
        description="Permanently delete a memory by name.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        call=_delete,
        destructive=True,
    ),
]

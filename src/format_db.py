"""File-format database — what each format is for, how to use it, what
tools handle it.

Two sources, merged at load time:
- **Bundled**: `data/file_formats.json` at the project root. Curated.
- **User**: `~/.config/TextView/file_formats.json`. Optional. User /
  agent additions; these win on id collision.

Lookup keys:
- `lookup_by_extension('.parquet')` — extension match (case-insensitive).
- `lookup_by_filename('Dockerfile')` — filename match for entries that
  declare `"filenames"`.
- `lookup_by_id('parquet')` — direct id match.

`search('keyword')` is a tiny ranker (substring + token match) over
name / description / tags / extensions.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


_BUNDLED = Path(__file__).resolve().parent.parent / "data" / "file_formats.json"
_USER = Path.home() / ".config" / "TextView" / "file_formats.json"


@dataclass
class FormatEntry:
    id: str
    name: str
    extensions: list[str] = field(default_factory=list)
    filenames: list[str] = field(default_factory=list)
    mime: list[str] = field(default_factory=list)
    category: str = "other"
    binary: bool = False
    description: str = ""
    magic_bytes: str = ""
    use_cases: list[str] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    open_with: str = ""
    convert: str = ""
    links: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "FormatEntry":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            extensions=[e.lower() for e in d.get("extensions", [])],
            filenames=[f.lower() for f in d.get("filenames", [])],
            mime=d.get("mime", []),
            category=d.get("category", "other"),
            binary=bool(d.get("binary", False)),
            description=d.get("description", ""),
            magic_bytes=d.get("magic_bytes", ""),
            use_cases=d.get("use_cases", []),
            tools=d.get("tools", []),
            open_with=d.get("open_with", ""),
            convert=d.get("convert", ""),
            links=d.get("links", []),
            tags=d.get("tags", []),
        )

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# {self.name}")
        if self.extensions or self.filenames:
            bits = ", ".join(f"`{e}`" for e in self.extensions + self.filenames)
            lines.append(f"\n*{bits}*")
        if self.category:
            lines.append(f"\n**Category:** {self.category}"
                         f"{' · binary' if self.binary else ' · text'}")
        if self.mime:
            lines.append(f"**MIME:** {', '.join(self.mime)}")
        if self.magic_bytes:
            lines.append(f"**Magic bytes:** `{self.magic_bytes}`")
        if self.description:
            lines.append(f"\n## Description\n\n{self.description}")
        if self.use_cases:
            lines.append("\n## Common uses\n")
            for u in self.use_cases: lines.append(f"- {u}")
        if self.open_with:
            lines.append(f"\n## How to open / inspect\n\n{self.open_with}")
        if self.convert:
            lines.append(f"\n## Conversion\n\n{self.convert}")
        if self.tools:
            lines.append("\n## Tools\n")
            for t in self.tools:
                kind = f" *({t.get('kind', '')})*" if t.get("kind") else ""
                if t.get("url"):
                    lines.append(f"- [{t.get('name', '?')}]"
                                 f"({t['url']}){kind}")
                else:
                    lines.append(f"- {t.get('name', '?')}{kind}")
        if self.links:
            lines.append("\n## Links\n")
            for l in self.links:
                lines.append(f"- [{l.get('title', l.get('url'))}]"
                             f"({l.get('url')})")
        if self.tags:
            lines.append(f"\n*Tags:* {', '.join(self.tags)}")
        return "\n".join(lines)

    def summary(self) -> str:
        """One-line summary for list views."""
        ext = self.extensions[0] if self.extensions else (
            self.filenames[0] if self.filenames else "")
        return f"{ext:14s}  {self.name}" if ext else self.name


class FormatDB:
    """Loaded file-format database. Cheap to construct — call `reload()`
    when the user / agent edits the user JSON."""

    def __init__(self):
        self.entries: list[FormatEntry] = []
        self.by_id: dict[str, FormatEntry] = {}
        self.by_ext: dict[str, FormatEntry] = {}
        self.by_filename: dict[str, FormatEntry] = {}
        self.reload()

    def reload(self):
        merged: dict[str, dict] = {}
        for src in (_BUNDLED, _USER):
            data = _read(src)
            if not data: continue
            for raw in data.get("formats", []):
                if not raw.get("id"): continue
                merged[raw["id"]] = raw       # user overrides bundled
        self.entries = [FormatEntry.from_dict(r) for r in merged.values()]
        self.by_id = {e.id: e for e in self.entries}
        self.by_ext = {}
        self.by_filename = {}
        for e in self.entries:
            for x in e.extensions: self.by_ext.setdefault(x, e)
            for f in e.filenames: self.by_filename.setdefault(f, e)

    def lookup_by_id(self, id_: str) -> FormatEntry | None:
        return self.by_id.get(id_)

    def lookup_by_extension(self, ext: str) -> FormatEntry | None:
        if not ext: return None
        if not ext.startswith("."): ext = "." + ext
        return self.by_ext.get(ext.lower())

    def lookup_by_filename(self, name: str) -> FormatEntry | None:
        return self.by_filename.get(name.lower())

    def search(self, query: str, limit: int = 20) -> list[FormatEntry]:
        q = query.lower().strip()
        if not q: return []
        scored: list[tuple[int, FormatEntry]] = []
        for e in self.entries:
            score = 0
            if q == e.id: score += 100
            if q in e.id: score += 30
            if q in e.name.lower(): score += 25
            for x in e.extensions:
                if q == x or q == x.lstrip("."): score += 60
                elif q in x: score += 15
            for f in e.filenames:
                if q == f: score += 50
                elif q in f: score += 12
            for t in e.tags:
                if q == t: score += 20
                elif q in t: score += 8
            if q in e.description.lower(): score += 5
            if q in e.category.lower(): score += 4
            if score > 0: scored.append((score, e))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [e for _, e in scored[:limit]]

    def categories(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries: out[e.category] = out.get(e.category, 0) + 1
        return dict(sorted(out.items(), key=lambda x: (-x[1], x[0])))


def _read(p: Path) -> dict | None:
    if not p.is_file(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None


# Global singleton — fine because this is read-mostly and small.
_DB: FormatDB | None = None


def db() -> FormatDB:
    global _DB
    if _DB is None: _DB = FormatDB()
    return _DB


def reload_db() -> FormatDB:
    """Force a reload of bundled + user files (e.g. after the agent
    appends a new entry to the user file)."""
    global _DB
    _DB = FormatDB()
    return _DB


def add_user_entry(entry: dict) -> tuple[bool, str]:
    """Append `entry` to the user JSON, replacing any existing entry with
    the same id. Returns (ok, message). Bumps reload."""
    if not entry.get("id"): return False, "entry needs `id`"
    _USER.parent.mkdir(parents=True, exist_ok=True)
    existing = _read(_USER) or {"schema_version": 1, "formats": []}
    formats = [f for f in existing.get("formats", [])
               if f.get("id") != entry["id"]]
    formats.append(entry)
    existing["formats"] = formats
    _USER.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    reload_db()
    return True, f"saved → {_USER}"

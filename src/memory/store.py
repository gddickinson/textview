"""File-based memory store.

One markdown file per memory at `~/.config/TextView/memory/<name>.md`,
with YAML frontmatter for metadata and a free-form body. `MEMORY.md`
in the same directory is auto-regenerated on every mutation; it's the
human-readable + LLM-loadable index.

Trust boundary: names are restricted to `[a-z0-9_-]{1,64}` so user /
LLM input can't escape the directory or alias the index.
"""
from __future__ import annotations  # `list[Memory]` annotations stay
                                    # strings so the `def list` method
                                    # doesn't shadow the builtin at
                                    # class-body evaluation time.
import re
import time
from pathlib import Path

from .types import Memory, VALID_TYPES, VALID_IMPORTANCE


MEMORY_DIR = Path.home() / ".config" / "TextView" / "memory"
INDEX_FILE = "MEMORY.md"

_NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)


def is_valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ""))


def slugify(text: str) -> str:
    """Convert arbitrary text to a safe memory name."""
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9_-]+", "_", s).strip("_")[:64]
    return s or "untitled"


class MemoryStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else MEMORY_DIR

    # -- core CRUD ---------------------------------------------------------

    def add(self, memory: Memory) -> Path:
        if not is_valid_name(memory.name):
            raise ValueError(f"invalid name: {memory.name!r}")
        if memory.type not in VALID_TYPES:
            raise ValueError(
                f"invalid type {memory.type!r} (use one of {sorted(VALID_TYPES)})")
        if memory.importance not in VALID_IMPORTANCE:
            raise ValueError(
                f"invalid importance {memory.importance!r}")
        self._ensure_dir()
        path = self._path(memory.name)
        if path.exists():
            raise FileExistsError(f"memory '{memory.name}' already exists")
        path.write_text(self._serialize(memory), encoding="utf-8")
        self._refresh_index()
        return path

    def get(self, name: str) -> Memory | None:
        if not is_valid_name(name):
            return None
        path = self._path(name)
        return self._parse(path) if path.exists() else None

    def list(self, type: str | None = None,
             importance: str | None = None) -> list[Memory]:
        if not self.root.exists():
            return []
        out: list[Memory] = []
        for p in sorted(self.root.iterdir()):
            if p.suffix.lower() != ".md" or p.name == INDEX_FILE:
                continue
            mem = self._parse(p)
            if mem is None:
                continue
            if type and mem.type != type:
                continue
            if importance and mem.importance != importance:
                continue
            out.append(mem)
        return out

    def search(self, query: str) -> list[Memory]:
        """Plain text scoring: name match (3x) > description (2x) > body
        (1x). Returns highest-scoring first. No ANN, no embeddings —
        cheap and good enough for hundreds of records."""
        q = (query or "").lower().strip()
        if not q:
            return self.list()
        scored: list[tuple[int, Memory]] = []
        for mem in self.list():
            score = 0
            if q in mem.name.lower():        score += 3
            if q in mem.description.lower(): score += 2
            if q in mem.content.lower():     score += 1
            if score:
                scored.append((score, mem))
        scored.sort(key=lambda t: -t[0])
        return [m for _, m in scored]

    def update(self, name: str, *, content: str | None = None,
               description: str | None = None,
               importance: str | None = None,
               type: str | None = None) -> Memory | None:
        mem = self.get(name)
        if mem is None:
            return None
        if content     is not None: mem.content     = content
        if description is not None: mem.description = description
        if importance  is not None:
            if importance not in VALID_IMPORTANCE:
                raise ValueError(f"invalid importance {importance!r}")
            mem.importance = importance
        if type        is not None:
            if type not in VALID_TYPES:
                raise ValueError(f"invalid type {type!r}")
            mem.type = type
        mem.last_used = time.time()
        self._path(name).write_text(self._serialize(mem), encoding="utf-8")
        self._refresh_index()
        return mem

    def touch(self, name: str) -> Memory | None:
        """Mark a memory as used — bump `last_used` + `use_count`. Called
        when a recall surfaces it. Useful for LRU compaction later."""
        mem = self.get(name)
        if mem is None:
            return None
        mem.last_used = time.time()
        mem.use_count += 1
        self._path(name).write_text(self._serialize(mem), encoding="utf-8")
        return mem

    def delete(self, name: str) -> bool:
        if not is_valid_name(name):
            return False
        path = self._path(name)
        if not path.exists():
            return False
        path.unlink()
        self._refresh_index()
        return True

    # -- index generation --------------------------------------------------

    def index_text(self, *, regenerate: bool = True) -> str:
        if regenerate:
            self._refresh_index()
        idx = self.root / INDEX_FILE
        return idx.read_text(encoding="utf-8") if idx.exists() else ""

    def _refresh_index(self):
        self._ensure_dir()
        memories = self.list()
        by_type: dict[str, list[Memory]] = {}
        for m in memories:
            by_type.setdefault(m.type, []).append(m)
        lines = [
            "# Memory index",
            "",
            f"_{len(memories)} memor{'y' if len(memories) == 1 else 'ies'} "
            f"in `{self.root}`. Auto-regenerated; manual edits are overwritten._",
            "",
        ]
        # Stable order: user / feedback / project / reference / session.
        for t in ("user", "feedback", "project", "reference", "session"):
            if t not in by_type:
                continue
            entries = sorted(by_type[t], key=lambda x: -x.last_used)
            lines.append(f"## {t.capitalize()} ({len(entries)})")
            lines.append("")
            for m in entries:
                star = " ⭐" if m.importance == "high" else ""
                desc = m.description or "_(no description)_"
                lines.append(f"- **{m.name}**{star} — {desc}")
            lines.append("")
        (self.root / INDEX_FILE).write_text(
            "\n".join(lines), encoding="utf-8")

    # -- internals ---------------------------------------------------------

    def _ensure_dir(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.md"

    def _serialize(self, mem: Memory) -> str:
        return (
            f"---\n"
            f"name: {mem.name}\n"
            f"type: {mem.type}\n"
            f"description: {mem.description}\n"
            f"importance: {mem.importance}\n"
            f"created: {mem.created}\n"
            f"last_used: {mem.last_used}\n"
            f"use_count: {mem.use_count}\n"
            f"---\n\n"
            f"{mem.content}"
        )

    def _parse(self, path: Path) -> Memory | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None
        body = text[m.end():].rstrip()
        meta: dict[str, str] = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        try:
            return Memory(
                name=meta.get("name", path.stem),
                type=meta.get("type", "session"),
                description=meta.get("description", ""),
                content=body,
                importance=meta.get("importance", "medium"),
                created=float(meta.get("created", "0") or 0),
                last_used=float(meta.get("last_used", "0") or 0),
                use_count=int(meta.get("use_count", "0") or 0),
            )
        except (ValueError, TypeError):
            return None

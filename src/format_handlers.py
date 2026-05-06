"""Persistent registry mapping file extensions to user-/agent-authored
scripts that can open them.

Stored as JSON at `~/.config/TextView/format_handlers.json`. The agent
calls `register_format_handler` to wire `.parquet → show_parquet` (a
saved agent script). On next open, TextView checks the registry and
runs the script with the file path as `argv[1]`. Output goes to the
runner panel.

Trust boundary: the script body is whatever the agent wrote, but
running it requires the same per-file run trust as F5 — the runner
prompts on first execution and remembers the user's answer.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path


def _registry_path() -> Path:
    return Path.home() / ".config" / "TextView" / "format_handlers.json"


@dataclass
class FormatHandler:
    extension: str       # ".parquet" (with the dot, lowercase)
    script: str          # name of an agent script (no .py suffix)
    description: str
    added_by: str = "agent"

    def to_dict(self) -> dict: return asdict(self)


# ---- registry I/O --------------------------------------------------------

def load() -> dict[str, FormatHandler]:
    p = _registry_path()
    if not p.is_file(): return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, FormatHandler] = {}
    if not isinstance(raw, dict): return out
    for ext, item in raw.items():
        if not isinstance(item, dict): continue
        try:
            out[ext.lower()] = FormatHandler(
                extension=ext.lower(),
                script=str(item.get("script", "")),
                description=str(item.get("description", "")),
                added_by=str(item.get("added_by", "agent")),
            )
        except Exception:
            continue
    return out


def save(handlers: dict[str, FormatHandler]):
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    serialized = {ext: h.to_dict() for ext, h in handlers.items()}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(serialized, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)


def register(extension: str, script: str, description: str = "",
             added_by: str = "agent") -> FormatHandler:
    """Add or update a handler. Returns the stored entry."""
    if not extension.startswith("."): extension = "." + extension
    h = FormatHandler(extension=extension.lower(), script=script,
                      description=description, added_by=added_by)
    handlers = load()
    handlers[h.extension] = h
    save(handlers)
    return h


def unregister(extension: str) -> bool:
    if not extension.startswith("."): extension = "." + extension
    handlers = load()
    if extension.lower() not in handlers: return False
    del handlers[extension.lower()]
    save(handlers)
    return True


def lookup(extension: str) -> FormatHandler | None:
    if not extension.startswith("."): extension = "." + extension
    return load().get(extension.lower())


def list_all() -> list[FormatHandler]:
    return sorted(load().values(), key=lambda h: h.extension)

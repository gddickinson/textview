"""Persistent storage for agent / user-authored scripts.

Scripts live in `~/.config/TextView/agent_scripts/` as `.py` (Python) or
`.sh` (shell). One file per script; the body is whatever the author
wrote, optionally prefixed with a `# description: …` comment that gets
surfaced in listings.

Names are restricted to `[A-Za-z][A-Za-z0-9_-]{0,63}` — no path
separators, no leading dot, max 64 chars. This is the trust boundary
that keeps `name="../../../etc/passwd"` from escaping the directory.

This module is the *storage* layer; the LLM-facing tools that wrap it
live in `llm/tools_scripts.py`. The chat-panel agent loop, the future
"Scripts" menu, and any plugin can all use this module directly.
"""
import re
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPTS_DIR = Path.home() / ".config" / "TextView" / "agent_scripts"


_LANG_TO_EXT = {
    "python": ".py",
    "shell":  ".sh",
}
_EXT_TO_LANG = {".py": "python", ".sh": "shell"}

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_DESC_RE = re.compile(r"^\s*#\s*description\s*:\s*(.+)$",
                      re.IGNORECASE | re.MULTILINE)


@dataclass
class Script:
    name: str
    language: str
    description: str
    body: str
    path: Path


def is_valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ""))


def _ensure_dir():
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(name: str, language: str) -> Path:
    return SCRIPTS_DIR / (name + _LANG_TO_EXT[language])


def _parse_description(body: str) -> str:
    """Look for a `# description: …` line in the first 20 lines."""
    head = "\n".join(body.splitlines()[:20])
    m = _DESC_RE.search(head)
    return m.group(1).strip() if m else ""


def list_scripts() -> list[Script]:
    """Every script in the directory, ordered by filename."""
    if not SCRIPTS_DIR.exists():
        return []
    out: list[Script] = []
    for p in sorted(SCRIPTS_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() not in _EXT_TO_LANG:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(Script(
            name=p.stem,
            language=_EXT_TO_LANG[p.suffix.lower()],
            description=_parse_description(text),
            body=text,
            path=p,
        ))
    return out


def read_script(name: str, language: str | None = None) -> Script | None:
    """Load a single script. If `language` is omitted, try both
    extensions and return whichever exists."""
    if not is_valid_name(name):
        return None
    candidates = ([_path_for(name, language)] if language in _LANG_TO_EXT
                  else [SCRIPTS_DIR / (name + ext) for ext in _EXT_TO_LANG])
    for path in candidates:
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            return Script(
                name=name,
                language=_EXT_TO_LANG[path.suffix.lower()],
                description=_parse_description(text),
                body=text,
                path=path,
            )
    return None


def write_script(name: str, language: str, body: str,
                 *, allow_overwrite: bool = True) -> Script:
    """Save a script. Default `allow_overwrite=True` lets `update_script`
    use the same path; pass `False` from `create_script` so first-write
    fails when the name is taken."""
    if not is_valid_name(name):
        raise ValueError(f"invalid script name: {name!r} "
                         f"(must match [A-Za-z][A-Za-z0-9_-]*, max 64)")
    if language not in _LANG_TO_EXT:
        raise ValueError(
            f"unknown language: {language!r} "
            f"(supported: {sorted(_LANG_TO_EXT)})")
    _ensure_dir()
    path = _path_for(name, language)
    if path.exists() and not allow_overwrite:
        raise FileExistsError(f"script already exists: {path}")
    # Prepend a small header if the body has no description and no shebang.
    body_to_write = body
    if not body.lstrip().startswith("#") and not _parse_description(body):
        header = (f"# created_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                  f"# created_by: TextView\n\n")
        body_to_write = header + body
    path.write_text(body_to_write, encoding="utf-8")
    return Script(
        name=name, language=language,
        description=_parse_description(body_to_write),
        body=body_to_write, path=path,
    )


def update_script(name: str, body: str) -> Script | None:
    """Replace the contents of an existing script (any language)."""
    s = read_script(name)
    if s is None:
        return None
    return write_script(name, s.language, body, allow_overwrite=True)


def delete_script(name: str) -> bool:
    """Remove every variant (`.py`, `.sh`) for the given name. Returns
    True if anything was deleted."""
    if not is_valid_name(name):
        return False
    deleted = False
    for ext in _EXT_TO_LANG:
        p = SCRIPTS_DIR / (name + ext)
        if p.exists():
            try:
                p.unlink()
                deleted = True
            except OSError:
                pass
    return deleted

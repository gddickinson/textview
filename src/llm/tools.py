"""Tool definitions for the LLM agent.

Each tool is a `Tool` instance with a JSON schema that gets passed to the
model and a `call(window, **args)` callable that runs on the Qt main
thread. Phase 2 = read-only tools: the model can examine the workspace
but can't mutate anything. Phase 3 will add `replace_selection`,
`run_command`, `change_setting`, etc.
"""
from pathlib import Path

from .tools_base import Tool
from .tools_module import MODULE_TOOLS
from .tools_scripts import SCRIPT_TOOLS_RO, SCRIPT_TOOLS_ACTION
from .tools_memory import MEMORY_TOOLS_RO, MEMORY_TOOLS_ACTION
from .tools_docs import DOC_TOOLS
from .tools_workspace import WORKSPACE_TOOLS
from .tools_inspect import INSPECT_TOOLS_RO, INSPECT_TOOLS_ACTION


# -- read-only implementations ------------------------------------------------


def _open_file(window, path: str):
    p = Path(path).expanduser()
    if not p.is_file():
        return f"Error: file not found: {p}"
    window.open_file(str(p))
    return f"Opened {p.name} ({window._current_format}, {len(window._current_content)} chars)."


def _read_current_file(window, max_chars: int = 50_000):
    window._sync_content()
    if not window._current_path:
        return "(no file currently open)"
    text = window._current_content or ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…[truncated; full size {len(window._current_content)} chars]"
    return f"path: {window._current_path}\nformat: {window._current_format}\n\n{text}"


def _read_selection(window):
    cur = window.viewer.code.textCursor()
    if not cur.hasSelection():
        return "(nothing selected)"
    text = cur.selectedText().replace(" ", "\n")
    return text


def _search_in_file(window, query: str, case_sensitive: bool = False) -> str:
    window._sync_content()
    text = window._current_content or ""
    if not text:
        return "(no content)"
    haystack = text if case_sensitive else text.lower()
    needle = query if case_sensitive else query.lower()
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        cmp = line if case_sensitive else line.lower()
        if needle in cmp:
            hits.append(f"{i}: {line}")
            if len(hits) >= 200:
                hits.append("…[truncated at 200 hits]")
                break
    return "\n".join(hits) if hits else "(no matches)"


def _list_dir(window, path: str = "."):
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        return f"Error: not a directory: {p}"
    entries = []
    for child in sorted(p.iterdir()):
        kind = "dir" if child.is_dir() else "file"
        size = child.stat().st_size if child.is_file() else ""
        entries.append(f"{kind}\t{child.name}\t{size}")
        if len(entries) >= 1000:
            entries.append("…[truncated]")
            break
    return f"path: {p}\n" + "\n".join(entries)


def _find_files(window, pattern: str, root: str | None = None):
    base = Path(root or (Path(window._current_path).parent
                         if window._current_path else Path.cwd())).expanduser()
    if not base.is_dir():
        return f"Error: not a directory: {base}"
    hits = list(base.rglob(pattern))[:500]
    return f"root: {base}\nmatches: {len(hits)}\n" + "\n".join(str(p) for p in hits)


def _get_metadata(window):
    if not window._current_path:
        return "(no file open)"
    from ..metadata import get_metadata
    sections = get_metadata(window._current_path, window._current_format)
    out = []
    for section, items in sections.items():
        out.append(f"[{section}]")
        for k, v in items.items():
            out.append(f"  {k}: {v}")
    return "\n".join(out)


# -- action implementations (Phase 3) -----------------------------------------

def _replace_selection(window, text: str):
    code = window.viewer.code
    if code.isReadOnly():
        return "error: editor is not in edit mode (Ctrl+E to enable)."
    cur = code.textCursor()
    if not cur.hasSelection():
        return "error: nothing is selected."
    cur.insertText(text)
    return f"replaced {cur.selectionEnd() - cur.selectionStart()} chars"


def _insert_text(window, text: str):
    code = window.viewer.code
    if code.isReadOnly():
        return "error: editor is not in edit mode (Ctrl+E to enable)."
    code.textCursor().insertText(text)
    return f"inserted {len(text)} chars"


def _save(window):
    if window._current_path is None:
        return "error: no file path; use save_as instead."
    if window.edit.save():
        return f"saved → {window._current_path}"
    return "error: save failed."


def _take_screenshot(window, path: str):
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    pix = window.viewer.active_widget().grab()
    if not pix.save(str(p)):
        return f"error: could not save image to {p}"
    return f"saved screenshot → {p}"


def _run_command(window, command: str, cwd: str | None = None):
    """Run a shell command in the embedded runner panel.

    The execution is async (QProcess); we return immediately with a
    confirmation. Output appears in the Terminal dock for the user to see.
    """
    window.run.panel.run_shell(command, cwd=cwd)
    return f"started: {command} (cwd={cwd or 'default'})"


def _run_python(window, code: str):
    window.run.panel.run_python_snippet(code)
    return f"started python snippet ({len(code)} chars)"


def _change_setting(window, key: str, value):
    """Whitelisted settings only — guards against the model toggling
    privacy-critical flags via prompt injection."""
    safe_keys = {
        "theme", "font_family", "font_size", "line_height", "padding",
        "word_wrap", "show_line_numbers", "show_whitespace",
        "highlight_current_line", "syntax_highlight", "render_markdown",
        "tab_width", "letter_spacing", "max_content_width", "text_align",
        "image_checkered_background", "trim_trailing_whitespace_on_save",
        "ensure_final_newline_on_save",
    }
    if key not in safe_keys:
        return f"error: '{key}' is not in the agent-settable allowlist."
    window.settings_manager.update(key, value)
    return f"set {key} = {value}"


# -- registry -----------------------------------------------------------------

READ_ONLY_TOOLS: list[Tool] = [
    Tool(
        name="open_file",
        description="Open a file in the viewer (replaces the current file). "
                    "Use this when the user asks to look at, edit, or view a different file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute path or ~-prefixed."}},
            "required": ["path"],
        },
        call=_open_file,
    ),
    Tool(
        name="read_current_file",
        description="Read the contents (or extracted text for documents) of the file "
                    "currently displayed in the viewer. Truncates very large files.",
        input_schema={
            "type": "object",
            "properties": {"max_chars": {"type": "integer", "default": 50000}},
        },
        call=_read_current_file,
    ),
    Tool(
        name="read_selection",
        description="Read the text the user has currently selected in the editor.",
        input_schema={"type": "object", "properties": {}},
        call=_read_selection,
    ),
    Tool(
        name="search_in_file",
        description="Find lines matching `query` in the current file. Returns line:text per hit.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "case_sensitive": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
        call=_search_in_file,
    ),
    Tool(
        name="list_dir",
        description="List entries in a directory.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
        call=_list_dir,
    ),
    Tool(
        name="find_files",
        description="Recursively find files matching a glob pattern (e.g. **/*.py).",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "root": {"type": "string", "description": "Defaults to current file's folder."},
            },
            "required": ["pattern"],
        },
        call=_find_files,
    ),
    Tool(
        name="get_metadata",
        description="Return per-format metadata (EXIF, PDF info, DOCX core props, etc.) "
                    "for the currently displayed file.",
        input_schema={"type": "object", "properties": {}},
        call=_get_metadata,
    ),
    *MODULE_TOOLS,
    *SCRIPT_TOOLS_RO,
    *MEMORY_TOOLS_RO,
    *DOC_TOOLS,
    *WORKSPACE_TOOLS,
    *INSPECT_TOOLS_RO,
]


ACTION_TOOLS: list[Tool] = [
    Tool(
        name="replace_selection",
        description="Replace the user's currently selected text with the given string. "
                    "Editor must be in edit mode (Ctrl+E).",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        call=_replace_selection,
        destructive=True,
    ),
    Tool(
        name="insert_text",
        description="Insert text at the editor's current cursor position.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        call=_insert_text,
        destructive=True,
    ),
    Tool(
        name="save",
        description="Save the current file to its existing path.",
        input_schema={"type": "object", "properties": {}},
        call=_save,
        destructive=True,
    ),
    Tool(
        name="take_screenshot",
        description="Capture the active viewer widget to an image file at `path`.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        call=_take_screenshot,
        destructive=True,
    ),
    Tool(
        name="run_command",
        description="Run a shell command in the Terminal panel. Output appears live "
                    "in the bottom dock. The command is not awaited — call again "
                    "later if you need the output.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "description": "Optional working directory."},
            },
            "required": ["command"],
        },
        call=_run_command,
        destructive=True,
    ),
    Tool(
        name="run_python",
        description="Run a Python snippet via the Terminal panel.",
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
        call=_run_python,
        destructive=True,
    ),
    Tool(
        name="change_setting",
        description="Update an allow-listed display/editor setting. Privacy and "
                    "security settings are NOT settable via this tool.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {},
            },
            "required": ["key", "value"],
        },
        call=_change_setting,
        destructive=True,
    ),
    *SCRIPT_TOOLS_ACTION,
    *MEMORY_TOOLS_ACTION,
    *INSPECT_TOOLS_ACTION,
]


def all_tools(include_actions: bool = False) -> list[Tool]:
    return list(READ_ONLY_TOOLS) + (list(ACTION_TOOLS) if include_actions else [])


def specs_for(provider_name: str, include_actions: bool = False) -> list[dict]:
    """Return the API-shape tool specs for the given provider."""
    tools = all_tools(include_actions=include_actions)
    if provider_name == "anthropic":
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
    if provider_name == "ollama":
        return [
            {"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.input_schema,
            }} for t in tools
        ]
    return []


def find_tool(name: str) -> Tool | None:
    for t in all_tools(include_actions=True):
        if t.name == name:
            return t
    return None

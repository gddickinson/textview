"""LLM tools for managing agent-authored scripts.

Read-only: `list_scripts`, `read_script`.
Destructive (require confirmation in the agent loop):
`create_script`, `update_script`, `delete_script`, `run_script`.

Storage is delegated to `agent_scripts`; this file is just the LLM
bridge — schema definitions + the thin `window`-aware wrappers that
the agent calls.
"""
from .tools_base import Tool
from .. import agent_scripts


def _list_scripts(window):
    scripts = agent_scripts.list_scripts()
    if not scripts:
        return "(no scripts saved)"
    lines = [f"{len(scripts)} script(s) in {agent_scripts.SCRIPTS_DIR}:"]
    for s in scripts:
        desc = f" — {s.description}" if s.description else ""
        lines.append(f"  {s.name}.{s.language[:2]}  ({s.language}){desc}")
    return "\n".join(lines)


def _read_script(window, name: str):
    s = agent_scripts.read_script(name)
    if s is None:
        return f"error: no script named '{name}'."
    return (f"name: {s.name}\nlanguage: {s.language}\n"
            f"path: {s.path}\n\n{s.body}")


def _create_script(window, name: str, language: str, body: str,
                   description: str = ""):
    if description and not body.lstrip().startswith("#"):
        body = f"# description: {description}\n" + body
    try:
        s = agent_scripts.write_script(name, language, body,
                                       allow_overwrite=False)
    except FileExistsError:
        return (f"error: script '{name}' already exists. Use "
                f"`update_script` to modify it, or `delete_script` first.")
    except (ValueError, OSError) as e:
        return f"error: {e}"
    return f"created {s.language} script '{s.name}' at {s.path}"


def _update_script(window, name: str, body: str):
    s = agent_scripts.update_script(name, body)
    if s is None:
        return f"error: no script named '{name}' to update."
    return f"updated '{s.name}' ({s.path})"


def _delete_script(window, name: str):
    if agent_scripts.delete_script(name):
        return f"deleted script '{name}'"
    return f"error: no script named '{name}' (or invalid name)."


def _run_script(window, name: str, args: list[str] | None = None):
    s = agent_scripts.read_script(name)
    if s is None:
        return f"error: no script named '{name}'."
    # Hand it to the existing Runner panel. `run_file` infers the
    # interpreter from the extension so .py and .sh both work; `args`
    # are appended after the file path so scripts can read sys.argv.
    try:
        window.run.panel.run_file(str(s.path), args=args)
    except Exception as e:
        return f"error: failed to start: {e}"
    suffix = f" with args {args}" if args else ""
    return f"started '{s.name}'{suffix} — output in the Terminal panel."


SCRIPT_TOOLS_RO: list[Tool] = [
    Tool(
        name="list_scripts",
        description="List the scripts saved in the agent script "
                    "directory. Returns name, language, and a short "
                    "description for each.",
        input_schema={"type": "object", "properties": {}},
        call=_list_scripts,
    ),
    Tool(
        name="read_script",
        description="Read the body of a saved script by name (without "
                    "extension). Returns metadata + full body.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        call=_read_script,
    ),
]

SCRIPT_TOOLS_ACTION: list[Tool] = [
    Tool(
        name="create_script",
        description="Save a new script. `name` must match "
                    "[A-Za-z][A-Za-z0-9_-]* (max 64). `language` is "
                    "'python' or 'shell'. Fails if a script with the "
                    "same name already exists; use `update_script` to "
                    "modify. Optionally include `description` for the "
                    "listing.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
                "body": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "language", "body"],
        },
        call=_create_script,
        destructive=True,
    ),
    Tool(
        name="update_script",
        description="Replace the body of an existing script.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["name", "body"],
        },
        call=_update_script,
        destructive=True,
    ),
    Tool(
        name="delete_script",
        description="Delete a saved script (every language variant).",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        call=_delete_script,
        destructive=True,
    ),
    Tool(
        name="run_script",
        description="Run a saved script. Output streams into the "
                    "Terminal panel. The script's interpreter is inferred "
                    "from its file extension (.py / .sh). Optional "
                    "`args` is a list of strings appended to the command "
                    "line so the script can read them via sys.argv.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
        call=_run_script,
        destructive=True,
    ),
]

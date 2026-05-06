# Agent-authored scripts

The chat agent (and you, manually) can save Python or shell scripts
to `~/.config/TextView/agent_scripts/` and re-run them later.

## Where they live

```
~/.config/TextView/agent_scripts/
  count_lines.py
  rename_files.sh
  …
```

Names are restricted to `[A-Za-z][A-Za-z0-9_-]{0,63}` so user input
can't escape into shell or path traversal.

## Frontmatter

Each script can start with a `# description: …` comment line. That
gets indexed and shown in the picker:

```python
# description: Count non-blank lines in sys.argv[1]
import sys
print(sum(1 for line in open(sys.argv[1]) if line.strip()))
```

## Running

- **F7** — opens a fuzzy picker over every saved script. Type to
  filter by name + description.
- **Scripts menu** — every script is a menu item; click to run.
- **Command palette** (Ctrl+K) — scripts appear here too.
- **Chat agent** — `run_script(name, args?)` from agent mode.

Output goes to the runner panel (the bottom dock) with ANSI color and
exit-code indicator.

## Tools the agent uses

- `list_scripts()` — names + descriptions
- `read_script(name)` — body
- `create_script(name, language, body, description?)` — language
  ∈ `{"python", "shell"}`. First-write requires user confirmation.
- `update_script(name, body)`
- `delete_script(name)` — confirmation required
- `run_script(name, args?)`

## Promotion path

If a saved script proves useful, you can move it into
`~/.config/TextView/plugins/` and add a `register(ctx)` to turn it
into a real plugin (with menu items, hooks, etc.). See **plugins.md**.

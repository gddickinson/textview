# TextView documentation

A modular PyQt6 GUI for viewing, editing, and analyzing text, code,
markup, document, image, video, table, and notebook files — with live
display configuration, syntax highlighting, LSP integration, an embedded
Jupyter notebook + REPL, agent-driven scripting, and a 170+ test
regression suite.

## For users

- **[overview.md](overview.md)** — the elevator pitch + what's where on
  screen.
- **[workspace-rag.md](workspace-rag.md)** — ask the agent about your
  whole project; every answer comes back with citations you can click.
- **[file-formats.md](file-formats.md)** — every format the viewer
  handles, what mode it opens in, and what edit/save means for each.
- **[unknown-files.md](unknown-files.md)** — what happens when you open
  a file TextView doesn't recognise; how the agent helps you handle it
  (and the safety gates around `pip install` / plugin creation).
- **[shortcuts.md](shortcuts.md)** — keyboard shortcuts grouped by
  context.
- **[notebook.md](notebook.md)** — embedded Jupyter notebook viewer +
  editor + runner.
- **[lsp.md](lsp.md)** — language servers (Python, TypeScript, Go, Rust,
  C / C++) — install, enable, troubleshoot.
- **[chat.md](chat.md)** — the LLM chat panel: providers, models, tools,
  memory.
- **[scripts.md](scripts.md)** — agent-authored scripts and the F7 picker.
- **[plugins.md](plugins.md)** — `~/.config/TextView/plugins/*.py` plugin
  loader and the `AppAPI` surface.
- **[hooks.md](hooks.md)** — file/run/chat lifecycle hooks.
- **[troubleshooting.md](troubleshooting.md)** — common gotchas with the
  fix for each.

## For agents (LLMs)

- **[agent-api.md](agent-api.md)** — the LLM tool surface and how to
  use it well.
- **[control-server.md](control-server.md)** — the external control
  protocol (drive the GUI from any process).
- **[architecture.md](architecture.md)** — how the modules fit together,
  where to find things.

## Index of features

| Topic | File |
| --- | --- |
| What this app is | [overview.md](overview.md) |
| Formats supported | [file-formats.md](file-formats.md) |
| Unknown files (agent-driven) | [unknown-files.md](unknown-files.md) |
| Keyboard reference | [shortcuts.md](shortcuts.md) |
| Notebooks (.ipynb) | [notebook.md](notebook.md) |
| LSP (hover, defn, refs, diagnostics) | [lsp.md](lsp.md) |
| Chat / LLM | [chat.md](chat.md) |
| Scripts | [scripts.md](scripts.md) |
| Plugins | [plugins.md](plugins.md) |
| Hooks | [hooks.md](hooks.md) |
| LLM tool surface | [agent-api.md](agent-api.md) |
| External control | [control-server.md](control-server.md) |
| Code map | [architecture.md](architecture.md) |
| Troubleshooting | [troubleshooting.md](troubleshooting.md) |

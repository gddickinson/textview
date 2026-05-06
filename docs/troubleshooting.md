# Troubleshooting

Common issues with the fix for each.

## Chat / LLM

### "kernel could not start" or "ipykernel not installed"
The notebook tried to launch a kernel using your configured Python
interpreter, which doesn't have `ipykernel`. Three paths:

1. **Run → Choose Python interpreter…** and pick a conda env / system
   Python that does have `ipykernel` (e.g. anaconda's base env).
2. `pip install ipykernel` in your current interpreter.
3. The app auto-falls-back to `sys.executable` (the one running
   TextView) — install ipykernel there if you want zero-config to
   "just work".

### Kernel starts but `import sqlite3` fails
This is the classic anaconda+macOS sqlite ABI mismatch:
`Symbol not found: _sqlite3_enable_load_extension`. Fix:

```
conda install sqlite        # or: conda update sqlite
```

The conda env shipped with this repo (`environment.yml`) pins
`sqlite>=3.45` from conda-forge, which has the symbol.

### Anthropic / OpenAI API key not found
Set it via Configuration panel → "Set API key…", or in your shell:

```
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
```

The chat panel checks keyring first, then env vars.

### Ollama: agent loops or repeats
Small local models (qwen2.5:7b, llama3.1:8b) have unreliable
tool-calling. The system-prompt nudge helps but isn't a cure. Use a
70B local model (llama3.1:70b) or switch to Anthropic / OpenAI for
multi-step plans.

## Notebook

### Cell ▶ Run does nothing
Should be impossible now — auto-start tries to spin up a kernel and
shows a status bar message either way. If you DO see silence, your
control server probably has a stale build; restart with the latest.

### Saved outputs don't appear after reopening
Cells store outputs in `cell["outputs"]` only after `end_run` fires.
If the kernel crashes mid-run, those outputs are lost. Run the cell
again.

### Cell source shows wrong text
You probably edited the source and the `textChanged` signal updated
`cell["source"]`. Reload the file (Ctrl+R) to discard.

## Edit / save

### "Edit mode" silently does nothing
The format you opened is read-only (PDF, DOCX, RTF, EPUB, ODT). Convert
to text first or open the source.

### Edits don't persist in the rendered view
For markdown / HTML, Ctrl+T twice to round-trip. For CSV, the cell
edits flow into the table model and the table-↔-code toggle updates
both directions. If something's stuck, **Reload** (Ctrl+R) discards
unsaved changes and re-reads the file.

## LSP

### Diagnostics never appear
Check the status bar after enabling LSP. "Started <lang>" means good;
"Could not start <lang>" means the binary isn't on PATH. See
**lsp.md** for install commands.

### Hover doesn't work
Cursor must be on an identifier and `lsp_enabled` must be on. For
auto-hover on cursor pause, also enable `lsp_hover_on_pause`.

## Performance

### Opening a large log file is slow
Files under 2 MB load fine. Larger logs go through line-by-line
syntax-highlighting which gets slow. The viewer doesn't yet have a
"large-file mode"; opening with syntax highlighting off in the config
panel helps.

### Search-in-project slow on big repos
The walker caps at 5000 hits and 2 MB per file. If your project is
huge, narrow with the file glob (e.g. `src/**/*.py`) before searching.

## GUI

### Window is invisible / blank on macOS
Make sure `QT_QPA_PLATFORM` is NOT set to `offscreen` in your shell.
That env var is fine for headless tests, but if you've exported it for
all of zsh, the GUI never shows.

### Dock layout reset after upgrade
Workspace persistence saves dock geometry/state to `QSettings`. If a
new dock is added in an update, the saved state may be incomplete.
View → reset each dock from the menu, or wipe the settings:
`defaults delete org.ClaudeText.TextView` (macOS) and relaunch.

## Tests

### `pytest` says "kernel could not start in this environment"
That's the slow tests gracefully skipping when sqlite3 is broken.
Either fix sqlite (see above) or run the fast subset:

```
python -m pytest -m "not slow"
```

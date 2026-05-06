# Plugins

Drop a `.py` file into `~/.config/TextView/plugins/` (or the project's
`plugins/` dir) and it loads on launch.

## Plugin contract

Each plugin module defines:

```python
def register(ctx):
    """Called once at startup. `ctx` is an AppAPI instance."""
    ctx.add_action(...)
    ctx.on("file_opened", my_handler)
    ...

def cleanup(ctx):
    """Called when plugins are reloaded. Optional."""
    ...
```

`AppAPI` (from `src/api.py`) is a stable façade over `MainWindow`.
Plugin code should never touch `MainWindow` directly so it doesn't
break when internals refactor.

## What `AppAPI` exposes

- **Files**: `open(path)`, `save()`, `current_path()`, `current_format()`
- **Tabs**: `tabs()`, `switch(path)`, `close(path)`
- **Editor**: `get_text()`, `set_text(text)`, `goto_line(n)`,
  `selected_text()`
- **Search**: `find(query)`, `replace_all(query, repl)`
- **Settings**: `get_setting(key)`, `set_setting(key, value)`
- **Run / shell**: `run_file(path)`, `run_shell(cmd)`
- **Tables**: `table_filter(col, op, val)`, `table_sort(col, asc)`,
  `table_data()`, `make_chart(...)`
- **Status**: `set_status(msg, ms?)`
- **Extension**: `add_action(text, handler, shortcut?, menu?)`,
  `add_dock(widget, area?)`, `remove_action(id)`, `remove_dock(id)`
- **Hooks**: `on(event, callback)` — events are
  `file_opened`, `file_saved`, `run_finished`, `chat_response`.
- **Escape hatch**: `window()` returns `MainWindow` for things the
  façade doesn't cover.

## Reloading

**Run → Reload plugins** disposes the current instances (calls
`cleanup`), drops them from `sys.modules`, and re-imports. Errors are
caught per-plugin so one broken file doesn't kill the rest.

## Example: save lines on save

```python
# ~/.config/TextView/plugins/line_count.py
def register(ctx):
    def on_save(path):
        n = sum(1 for _ in open(path))
        ctx.set_status(f"saved {n} lines → {path}", 3000)
    ctx.on("file_saved", on_save)
```

## Sample plugin

The repo ships a sample at `plugins/sample_plugin.py`. Read it for a
working pattern.

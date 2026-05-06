# Hooks

Lifecycle hooks let you run arbitrary Python in response to file /
run / chat events. Each hook is a `.py` file in
`~/.config/TextView/hooks/`.

## Recognized handler names

Define one or more of these top-level functions in your hook file:

```python
def on_file_opened(path, **kw): ...
def on_file_saved(path, **kw): ...
def on_run_finished(exit_code, status, **kw): ...
def on_chat_response(message, **kw): ...
```

If your handler accepts `api=`, it gets the `AppAPI` instance:

```python
def on_file_saved(path, api=None, **kw):
    api.set_status(f"hook: saved {path}")
```

## Loading

Hooks are loaded once at startup. **Run → Reload scripting hooks**
re-imports them all. Errors are caught per-handler so one broken hook
doesn't stop the others.

## Quick start

**Run → Show hooks folder** opens `~/.config/TextView/hooks/` in your
file manager. There's a sample written on first launch:

```python
# ~/.config/TextView/hooks/example.py
def on_file_opened(path, **kw):
    print(f"opened {path}")

def on_file_saved(path, **kw):
    print(f"saved {path}")
```

## Hooks vs plugins

| | Hooks | Plugins |
| --- | --- | --- |
| Registration | implicit (function name) | explicit `register(ctx)` |
| Lifecycle | reload only | reload + cleanup |
| UI | none | can add menus, docks |
| Use case | event-driven side effects | full features |

# Control server (external GUI control)

Drive every GUI operation from another process. Useful for end-to-end
testing, scripting, and remote LLM control.

## Starting it

```
python main.py --control-port 4242
```

Server listens on TCP `127.0.0.1:<PORT>` only. There's no auth —
loopback is the trust boundary.

## Protocol

Line-delimited JSON. One request per line, one reply per line.

```json
→ {"op": "open_file", "args": {"path": "/tmp/x.md"}}
← {"ok": true,  "result": {...}}
← {"ok": false, "error": "...", "trace": "..."}
```

## Operations

| op | args | effect |
| --- | --- | --- |
| `state` | — | path / format / mode / editing / modified / buffer_len |
| `open_file` | `{path}` | load a file |
| `save` | — | save through `EditController` |
| `save_as` | `{path}` | save to a specific path |
| `set_text` | `{text, enter_edit?}` | overwrite buffer (default enters edit mode) |
| `get_text` | — | buffer + current_content + first 500 chars |
| `enter_edit` / `exit_edit` | — | toggle edit mode |
| `trigger_action` | `{name}` | fire any `MainWindow.action_*` |
| `list_actions` | — | every registered action with shortcut |
| `setting` | `{key}` | read a `DisplaySettings` field |
| `set_setting` | `{key, value}` | write one |
| `refresh` | — | call `_refresh_view()` |
| `screenshot` | `{path}` | write a PNG of the main window |
| `eval` | `{code}` | run with `w` bound to MainWindow; returns `repr` |

## Python client

```python
from tools.control_client import Client

with Client(port=4242) as c:
    print(c.call("state"))
    c.call("open_file", path="/tmp/x.md")
    c.call("trigger_action", name="action_toggle_render")
    c.call("screenshot", path="/tmp/s.png")
```

Or the CLI:

```
python tools/control_client.py state
python tools/control_client.py trigger_action --name action_toggle_render
python tools/control_client.py eval --code 'w.viewer.mode()'
```

## Use cases

- **Smoke testing** the GUI from CI without `pytest-qt` setup.
- **Driving from an external LLM** that can't run inside the Qt
  process — e.g. agents that need to control multiple apps.
- **Reproducible bug reports** — paste a sequence of ops + the
  resulting screenshots.

## Caveats

- Modal dialogs (`QFileDialog`, `QMessageBox`, etc.) BLOCK the Qt
  event loop, so any control request during a modal hangs. The
  built-in ops avoid this — `enter_edit` checks `can_edit` first
  rather than letting the read-only-format dialog block.
- The server runs in the main Qt event loop, so each request is
  serialized. A long-running `eval` blocks the GUI for its duration.

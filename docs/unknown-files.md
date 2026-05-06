# Unknown files — agent-driven file discovery

When TextView opens a file it doesn't natively understand, it doesn't
just throw bytes on screen. It identifies the file (magic bytes,
extension hints, heuristics), shows a markdown report with the size,
detected kind, hex preview, and a suggested next step — and invites
you to ask the agent.

## What the report looks like

For an unknown file (say `data.parquet`), opening it shows a rendered
markdown page with:

- **File**: name, absolute path, size, modification time.
- **Detected kind**: e.g. `parquet (Apache Parquet columnar data)`.
- **Detected via**: `magic bytes` / `extension` / `heuristic`.
- **Hex preview**: first 256 bytes side-by-side with ASCII.
- **Encoding guess** (for text-like files): UTF-8 / Latin-1 / etc.
- **Suggested action**: "ask the agent — try `analyze_file('data.parquet')`".
- **Registered handler**: if you (or the agent) have already wired a
  script to this extension, it's noted here.

If it turns out to be plain text after all (no binary bytes, decodes
cleanly), the report is skipped and the file opens in the normal text
view.

## Letting the agent help

Open the chat panel (Ctrl+J) and ask "what is this?" or "how do I open
this?". The agent has these tools:

| Tool | What it does | Gate |
| --- | --- | --- |
| `analyze_file` | Re-runs the file inspector and returns the structured report. | read-only |
| `web_search` | DuckDuckGo HTML scrape — no API key needed. | read-only |
| `list_format_handlers` | Lists every `(extension → script)` mapping. | read-only |
| `list_plugins` | Lists every plugin file in `~/.config/TextView/plugins/`. | read-only |
| `register_format_handler` | Wires a saved agent script to an extension. | "Allow actions" |
| `unregister_format_handler` | Removes a registered handler. | "Allow actions" |
| `create_plugin` | Writes a new plugin file. | "Allow actions" + `agent_can_create_plugins` |
| `install_package` | `pip install` a package. | "Allow actions" + `agent_can_install` |

## Two-gate safety

The agent **cannot** install packages or write plugins by default. Both
require *two* approvals:

1. **Chat panel "Allow actions" checkbox** — gates every action tool.
2. **A per-tool setting flag** — `agent_can_install` and
   `agent_can_create_plugins`, both off by default. Flip them in the
   Configuration panel only when you trust what the agent is about
   to do, and turn them off again afterward.

Why two gates? Plugins run on every app launch with full Python
access; pip-installing arbitrary code can do anything the user can do.
The chat-panel checkbox covers the *session*; the settings flag covers
the *capability*. Either gate, when off, means "no" — so even if
"Allow actions" is on, an agent that tries to install a package
without `agent_can_install` will get an explanatory error directing
it to ask you.

`register_format_handler` only requires "Allow actions" — it just
points an extension at a script you've already approved. Same for
`unregister_format_handler`.

## Workflow: opening a parquet file

1. You drop `sales.parquet` onto TextView. It shows the unknown-file
   report with `detected_kind: parquet`.
2. You open the chat panel and ask "open this".
3. The agent calls `analyze_file` → confirms parquet.
4. It calls `list_workspace` to see if other parquet files are around,
   then `list_format_handlers` (none registered).
5. It proposes a plan: "I'll write a `show_parquet` script that uses
   `pyarrow` to read the file and print a head + schema. I'll register
   it for `.parquet`. To run pyarrow, I need to install it with `pip
   install pyarrow` — that needs `agent_can_install`."
6. You enable `agent_can_install` in the Configuration panel.
7. The agent calls `install_package('pyarrow')`, then `create_script`
   (gated only by "Allow actions"), then `register_format_handler`.
8. You disable `agent_can_install` again.
9. Next time you open a `.parquet` file, the script runs automatically
   and shows you a head + schema.

## What the agent can NOT do

- It cannot bypass the per-tool settings gates by retrying — they're
  enforced before the subprocess/file write runs, and the error
  message tells it to ask you.
- It cannot write plugins to arbitrary paths — names must match
  `[A-Za-z][A-Za-z0-9_]{0,63}`, so `../escape` is rejected.
- It cannot pip-install arbitrary strings — package names are matched
  against `[A-Za-z][A-Za-z0-9._-]{0,63}` (no shell metacharacters,
  no URLs, no version specifiers).
- It cannot overwrite an existing plugin without you deleting it
  first.

## Format-handler scripts

A format handler is just an agent script that takes the file path as
its first argument:

```python
# description: parquet head + schema
import sys, pyarrow.parquet as pq
t = pq.read_table(sys.argv[1])
print(t.schema)
print(t.to_pandas().head(20))
```

Save it as `show_parquet` via the agent's `create_script` tool, then
call `register_format_handler(".parquet", "show_parquet")`. From then
on, opening a `.parquet` file invokes the script's stdout in the
runner panel.

## Where things live

- File inspector: `src/file_inspector.py` (logic) →
  `MainWindow.open_file` route in `src/app.py` (wiring).
- Format-handler registry: `~/.config/TextView/format_handlers.json`.
- Agent scripts: `~/.config/TextView/agent_scripts/*.py`.
- Plugins: `~/.config/TextView/plugins/*.py`.
- Web search: `src/web_search.py` (DuckDuckGo HTML, no key).
- OCR (optional): `src/ocr.py` — `pip install pytesseract pdf2image` +
  the `tesseract` and `poppler` system packages.

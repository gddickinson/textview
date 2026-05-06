# Overview

TextView is a PyQt6 desktop app that opens almost any file you'd
encounter on a developer's machine and shows it the right way: code in a
syntax-highlighted editor, markdown rendered, PDFs paginated, images
zoomable, CSVs as a sortable spreadsheet, notebooks as runnable cells,
unknown formats identified by magic bytes. It also edits and saves
most of those formats, runs scripts in 30+ languages, talks to
language servers, embeds a Jupyter kernel, and exposes everything
through an LLM chat panel (with workspace RAG + multimodal input) and
an external control socket. A layered security pipeline scans every
file before opening; quarantine + optional `clamscan` / sandboxing
provide further depth.

## What's on the screen

```
┌──────────────────────────────────────────────────────────────────────┐
│ menubar:  File  Edit  Run  View  Image  Media  Table  Scripts  …    │
├──────────────────────────────────────────────────────────────────────┤
│ toolbar:  Open  Save  Reload  Zoom-  Zoom+  Find  Edit  Toggle  …   │
├──────────────────────────────────────────────────────────────────────┤
│ tabs:    [welcome]  [file.md]  [data.csv]  …                        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│             V I E W E R   ( current file )                           │
│                                                                      │
│  one of: code editor / rendered HTML / PDF / image / video /         │
│          table / notebook / browser                                  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│ statusbar: Welcome (untitled)            Format: markdown  utf-8    │
└──────────────────────────────────────────────────────────────────────┘
```

Side / bottom docks (toggle from View menu):

- **Configuration** (Ctrl+,) — typography, theme, layout, display flags, security toggles
- **Metadata** (Ctrl+I) — EXIF / PDF info / DOCX props for the open file
- **Chat** (Ctrl+J) — LLM chat with tool access (workspace search, file ops, format DB, security)
- **Citations** (Ctrl+Shift+Z) — ranked file matches from the agent's last workspace query (click to jump)
- **Project** (Ctrl+Shift+P) — file tree of a folder
- **Image adjustments** (Ctrl+Shift+M) — sliders + frame nav + histogram
- **Spreadsheet** (Ctrl+Shift+E) — selection stats, edit toggle, charts
- **Diagnostics** (Ctrl+Shift+X) — LSP problems list
- **Terminal** (Ctrl+\`) — full PTY terminal (vim, top, etc. work)
- **Jupyter** (Ctrl+Alt+J) — embedded qtconsole

Modal references (Help menu):

- **File formats database** (Ctrl+Shift+B) — searchable card per format
- **Security report** (F8) — re-scan the current file
- **Quarantined files** — restore / permanently-delete entries
- **Cheat sheet** (Ctrl+?) — every keyboard shortcut

## Modes

The viewer is a stack widget. Only one mode is shown at a time.

| Mode | Used for |
| --- | --- |
| `code` | text/code/data formats with syntax highlighting + line numbers |
| `rendered` | markdown / HTML / DOCX / EPUB / ODT — visual rendering |
| `pdf` | native PDF rendering with text selection + search |
| `image` | image viewer with zoom / rotate / multi-frame nav / histogram |
| `video` | video playback with transport controls |
| `table` | CSV/TSV spreadsheet with sort / filter / charts |
| `notebook` | Jupyter `.ipynb` viewer + editor + runner |
| `web` | embedded Chromium for URLs and HTML |

`Ctrl+T` toggles between a format's primary mode and its alternate
(usually `rendered ↔ code`, or `pdf ↔ code`, or `table ↔ code`). Image,
video, and notebook formats have no alternate so toggle is a no-op.

## Edit mode

For editable formats, **Ctrl+E** flips the editor between read-only and
editable. **Ctrl+S** saves. The status bar shows `[edit]` and `●` if the
buffer is dirty. Document formats (PDF, DOCX, RTF, EPUB, ODT) refuse
edit mode.

For CSVs the table cells are editable when the spreadsheet panel's
"Cells editable" checkbox is on (default off, double-click to edit).
Edits in the table propagate to the code view and vice-versa.

For notebooks, code cells are always editable; markdown cells get an
"Edit" button to toggle between rendered and source view.

## The agent

`Ctrl+J` opens the chat panel. Provider-agnostic — Anthropic, OpenAI,
Ollama, Gemini. The agent has read-only tools by default; toggle
**Allow actions** to enable the destructive ones (each gated
separately). Tool surface includes:

- `query_workspace`, `index_workspace`, `list_workspace` — BM25 search
  over the active project; results auto-populate the Citations dock.
- `lookup_format`, `search_formats`, `list_format_categories` — built-in
  reference for 40+ file formats.
- `scan_file`, `list_quarantined`, `quarantine_file`,
  `restore_quarantined`, `delete_quarantined` — security ops.
- `analyze_file`, `register_format_handler`, `create_plugin`,
  `install_package`, `web_search` — the unknown-file workflow.
- `read_doc`, `search_docs`, `list_docs` — query this very docs folder.
- File / tab / editor / table operations — get_text, set_text, save,
  goto_line, apply_table_filter, sort_table, make_chart, …

Two-gate safety: the chat-panel "Allow actions" checkbox covers the
session, and a per-tool settings flag (`agent_can_install`,
`agent_can_create_plugins`, `agent_can_purge_quarantine`) covers the
capability. Either off means "no". See `agent-api.md` for the full
list.

## File loading is scanned

By default every file is heuristic-scanned before opening — dangerous
extensions, magic-byte vs extension mismatches, Office macros, PDF
JavaScript, suspicious shell patterns. Findings of severity
warning/dangerous prompt with **Open / Quarantine / Cancel**. Toggle
in Configuration → Privacy & Security → File-loading security. See
`security.md` for the full threat model.

## What this isn't

- Not a full IDE — there's no project-build system, debugger, or
  terminal multiplexing.
- Not a browser — the embedded `QWebEngineView` is for previewing and
  rendering, not daily browsing.
- Not a monolithic editor — everything is a separate Qt widget you can
  rearrange, dock, or hide.

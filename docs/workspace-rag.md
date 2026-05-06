# Workspace RAG (ask the agent about your files)

Drop a folder into TextView, then ask the chat agent anything about
its contents. Every answer comes back with `(file, locator, snippet)`
citations you can click to open the underlying file at the right
line / page / cell.

## How it works

When the agent calls `query_workspace("…")`:

1. The walker crawls the active project root (or one you specify),
   skipping `.git`, `node_modules`, `__pycache__`, `.venv`, etc.
2. Each file is chunked by format-natural units:
   - **text / code** — groups of ~40 lines, with a small overlap.
   - **PDF** — one chunk per page (text extracted via `pypdf`).
   - **notebook** — one chunk per cell.
   - **image** — one filename-level chunk (vision tools cover content).
3. A BM25 inverted index ranks chunks against the query.
4. The top-K results are pushed to the **Citations** dock and
   returned to the agent as JSON it can cite in its answer.
5. Click any citation → `open_at_locator(path, locator)` opens the
   file in the right viewer mode and jumps to the right spot.

## Where the index lives

`~/.cache/TextView/workspace_index/<root_hash>.pkl` — pickled
`WorkspaceIndex` keyed on the project root path. Repeat queries
are instant; the cache invalidates if any source file's mtime is
newer than the cache file, or if the index format version bumps.

To force a rebuild, ask the agent to call `index_workspace(force=True)`.

## What's NOT indexed (yet)

- Files >4 MB (configurable via `_MAX_FILE_BYTES` in
  `src/workspace_index.py`).
- More than 20 000 files per workspace.
- Image-only PDFs (no OCR).
- Vector embeddings — current search is lexical (BM25) only.
  Embeddings can plug in later by replacing `BM25Index`.

## Tools surface

- `list_workspace(root?)` — file-count by extension. Cheap; use
  before answering "what's in this project".
- `index_workspace(root?, force=false)` — build/refresh the index.
- `query_workspace(query, k?, root?)` — search; returns ranked
  snippets plus pushes citations to the panel.

## Citations panel

**Ctrl+Shift+Z** toggles the dock. Each row shows:
```
src/foo.py  ·  line:42
    def special_marker(): return 42
```

Activating a row (Enter or double-click) calls `open_at_locator`,
which knows how to:

- jump the code editor to a line (`line:N`)
- navigate the PDF view to a page (`page:N`)
- focus a cell in the notebook view (`cell:N`)
- just open the file (`""` / file-level)

## Why this design

Most AI products are chat-only and your only feedback is the
agent's *summary* of a source. Here, every answer is grounded in a
specific spot in a specific file, and you can verify or extend with
one click. That's the wedge.

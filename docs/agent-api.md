# Agent (LLM) tool surface

This is the reference for the LLM chat panel's tools. Tools are split
into **read-only** (always safe; not gated by confirmation) and
**action** (edits files / spawns processes / mutates state — gated by
the user's "Allow agent actions" confirmation flow).

The chat is at **Ctrl+J**. Tools are exposed automatically based on
the active provider's tool-calling capability (Anthropic, OpenAI, and
Ollama all support it; some local Ollama models have flaky
tool-calling — there's a system-prompt nudge that helps).

## Read-only tools

### File / project introspection
- `read_file(path)` — return text content + format tag.
- `list_dir(path?)` — list files in a directory (defaults to the
  current project root or active file's folder).
- `current_file()` — path, format, mode, dirty state of the active tab.
- `find_in_file(query, regex?, case?)` — search the active buffer.

### Tables
- `table_summary()` — header, row count, numeric columns, first 5 rows.
- `compute_stats(column)` — count / mean / median / stddev / min / max
  / Q1/Q3 / skew / kurtosis for numeric columns; uniqueness for strings.
- `correlation_matrix()` — pairwise Pearson on every numeric column.

### Structured-data formats (v3.4)
The agent has first-class tools for every binary table-shaped format
TextView reads. Each returns a schema overview + 20-row CSV preview
(deliberately truncated so a 50M-row dataset doesn't burn context).
- `read_spreadsheet(path, sheet?)` — XLSX / ODS / XLS, multi-sheet.
- `read_sqlite(path)` — schema overview (tables + columns + row counts).
- `query_sqlite(path, sql)` — ad-hoc SELECT, read-only enforced.
- `read_archive(path)` — ZIP / TAR / 7z member listing.
- `read_array_file(path, name?)` — NumPy `.npy` / `.npz` + MATLAB `.mat`.
- `read_parquet(path)` — Parquet / Feather.
- `read_hdf5(path, dataset?)` — HDF5 / NetCDF, group tree flattened.
- `read_cert(path)` — X.509 certificate or PEM key metadata. **Never
  displays raw private-key material.**

### Documentation (this set!)
- `list_docs()` — every documentation page with a one-line description.
- `read_doc(name)` — full markdown of a doc page (e.g. `"file-formats"`).
- `search_docs(query)` — keyword search across all docs; returns
  `(name, line_no, snippet)` triples.

### Workspace RAG (the main differentiator)
- `list_workspace(root?)` — count of files by extension in the
  project. Cheap; call this before answering "what's in this project".
- `index_workspace(root?, force?)` — build/refresh a BM25 index over
  every text/code/PDF/notebook file. Caches to disk.
- `query_workspace(query, k?)` — ranked snippets with **clickable
  citations**: each result has `(path, locator, snippet)` and the
  citation panel auto-populates so the user can verify by clicking.
  USE THIS for any "where is X / find Y / how does Z work" question
  — never guess; cite specific files.

### Memory store
- `memory_index()` — every saved memory's name + description.
- `memory_recall(query)` — semantic-ish keyword search.

### Scripts
- `list_scripts()` — every saved agent script's name + description.
- `read_script(name)` — script body.

## Action tools (require confirmation by default)

### File mutation
- `write_file(path, content)` — overwrite or create a file.
- `apply_patch(path, search, replace)` — exact-text replacement.

### Module control (drives the GUI)
- `switch_tab(path_or_index)` — focus a tab.
- `goto_line(line)` — jump in active editor.
- `apply_table_filter(column, op, value)` — filter the spreadsheet
  view (operators: `~`, `=`, `!=`, `>`, `>=`, `<`, `<=`).
- `clear_table_filter()`.
- `sort_table(column, ascending?)`.
- `make_chart(x, y, kind, save_path?)` — Line / Bar / Scatter /
  Histogram / Pie / Box / Heatmap / Correlation matrix / Dual axis.
- `add_derived_column(name, formula)` — formula sees column names as
  variables; sandboxed (no `__builtins__`).

### Memory
- `memory_save(name, type, importance, body, description?)` —
  type ∈ `{user, project, reference, feedback, session}`.
- `memory_update(name, body? description?)`.
- `memory_delete(name)`.

### Scripts
- `create_script(name, language, body, description?)` — new
  `~/.config/TextView/agent_scripts/<name>.{py|sh}`.
- `update_script(name, body)`.
- `delete_script(name)`.
- `run_script(name, args?)` — execute via the Runner.

## How to use them well

**Always read state before assuming**: a previous turn's tool result
may have been clipped or overwritten by user actions. `current_file()`
+ `table_summary()` are cheap.

**Don't guess the active file**: ask via `current_file()` first.

**For data analysis**:
1. `table_summary()` — see what columns exist and their types.
2. `compute_stats(col)` for a quick read.
3. `correlation_matrix()` if there are ≥2 numeric columns.
4. `make_chart(...)` to render. Save to `save_path` if you want the
   user to see a real PNG; otherwise the chart appears in the panel.

**For code reading**:
1. `current_file()` — confirm we're looking at what the user expects.
2. `read_file(path)` for other files.
3. `find_in_file("def something")` — scoped search.

**For multi-step plans (Ollama / smaller models)**:
- Emit one tool per turn, wait for the result, then plan the next.
- Don't batch multiple `tool_calls` — the dispatcher serializes them
  anyway and small models tend to repeat dropped calls.
- After `sort_table` / `apply_table_filter`, re-read the data via
  `table_summary()` before citing top/bottom rows.

## When the user asks "what can you do here"

The right answer is: read `INDEX.md` via `read_doc("INDEX")` and
respond from that, not from your training prior. The docs are the
authoritative source for current capability.

## When the user asks about their files

**Always cite specific files.** Don't summarize from general knowledge.
Concretely:

1. `list_workspace()` to see what kinds of files are around.
2. `query_workspace("the relevant query")` to find specific spots.
3. Reference the file paths and locators in your response. Saying
   "I found `def special_marker` at `src/foo.py:42`" lets the user
   click the citation panel row to verify. Saying "your code defines
   a special_marker function" without a citation is worse — they
   have to take it on faith.

For images: the user can attach an image to their message via the
📎 button in the chat. When they do, the message is multimodal and
you can see the image directly. Ask for an attachment if they're
discussing visual content.

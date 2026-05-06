# Notebooks (.ipynb)

TextView has an in-app notebook viewer + editor + runner — no need
to leave for `jupyter notebook` or `jupyter lab` for basic flows.

## Opening

Double-click an `.ipynb`, or **File → Open**, or drag-and-drop. It
opens in `notebook` mode showing one `CellWidget` per cell.

## Cell types

- **Code cells** — editable monospace input + a "▶ Run" button + an
  output area. Header shows `In [n]:` (saved exec count) or `In [*]:`
  while running.
- **Markdown cells** — rendered HTML by default. The "Edit" button
  swaps in a source `QPlainTextEdit`; clicking again rerenders.

## Running cells

- Click ▶ Run, or use the menus:
  - **Run → Notebook: run all cells** (Ctrl+Alt+R)
- The first run **auto-starts a kernel** with the configured Python
  interpreter (see **Run → Choose Python interpreter…**). If that
  fails, it falls back to `sys.executable` (the env running the app).

If neither works, the cell shows a red error and the status bar
explains what's missing — usually `pip install ipykernel` in your
chosen interpreter.

## Output rendering

Live iopub messages and saved-cell outputs both go through a priority
dispatch: `text/html` → `image/svg+xml` → `image/png` → `image/jpeg` →
`text/markdown` → `text/plain`. So matplotlib figures, pandas HTML
tables, etc. render in-cell.

## Editing

- Code cells: just type. Edits sync into the cell dict.
- Markdown cells: click "Edit" to switch to source mode; type;
  click "Done" to render again.
- **Ctrl+S** saves the notebook back to disk via `nbformat.write`,
  including any new outputs from cells you ran.

## Cell mutations (Run menu)

- **Notebook: add code cell below** / **add markdown cell below**
- **Notebook: delete current cell** (cell with keyboard focus)
- **Notebook: change cell to code / markdown**
- **Notebook: move cell up** (Ctrl+Alt+↑) / **down** (Ctrl+Alt+↓)
- **Notebook: start kernel** / **run all cells** (Ctrl+Alt+R)

## Kernel management

The kernel runs as a subprocess of the chosen interpreter via
`<interpreter> -m ipykernel_launcher`. To switch interpreters mid-session,
**Run → Choose Python interpreter…** lists every conda env / pyenv
version / system Python it can find. Selection persists across sessions.

For a richer interactive console, **Run → Open Jupyter console**
(Ctrl+Alt+J) opens an embedded `qtconsole.RichJupyterWidget` with its
own kernel and toolbar (Restart, Interrupt, Pick kernel).

## Caveats

- **Editing input source while a cell is running**: works, but the
  iopub messages from the running cell still attach to that cell. You
  won't lose them.
- **Modal kernel restarts**: shutting down a notebook view kills its
  kernel; reopen any time.
- **Nbformat ID warnings**: nbformat 5.10+ wants `cell.id` fields; if a
  hand-written notebook is missing them, you get a warning at write
  time but the save succeeds.

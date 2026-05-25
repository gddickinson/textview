# Keyboard shortcuts

Press **Ctrl+?** in the app for a live, auto-generated cheat sheet
based on the actual `QAction` registrations. The list below is the
canonical reference.

## File

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Open file |
| Ctrl+L | Open URL |
| Ctrl+P | Quick open file in project |
| Ctrl+Shift+O | Open folder (project root) |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save as |
| Ctrl+R | Reload current |
| Ctrl+W | Close current tab |
| Ctrl+Alt+Shift+W | Close all tabs |
| Ctrl+N | New tab (welcome) |
| Ctrl+Alt+N | **New from template…** (Markdown / Python / LaTeX / Dockerfile / …) |
| Ctrl+Shift+N | New window |
| Ctrl+Q | Quit |

## Edit / Search

| Shortcut | Action |
| --- | --- |
| Ctrl+E | Toggle edit mode |
| Ctrl+F | Find / replace bar |
| Ctrl+Shift+F | Find in project |
| Ctrl+G | Go to line |
| Ctrl+/ | Toggle line comment |
| Ctrl+Shift+L | Select line |
| Ctrl+Shift+D | Duplicate line |
| Alt+Up / Alt+Down | Move line up / down |
| Ctrl+; | Insert snippet |
| Ctrl+K | Command palette |

## View

| Shortcut | Action |
| --- | --- |
| Ctrl+T | Toggle rendered ↔ code (or PDF/table ↔ code) |
| Ctrl++ / Ctrl+- | Zoom in / out |
| Ctrl+0 | Reset zoom (or fit-to-window for images) |
| Ctrl+, | Configuration panel |
| Ctrl+I | Metadata panel |
| Ctrl+Shift+P | Project panel |
| Ctrl+Shift+M | Image adjustments panel |
| Ctrl+Shift+E | Spreadsheet panel |
| Ctrl+Shift+X | Diagnostics panel |
| Ctrl+\` | Terminal |
| Ctrl+Alt+J | Jupyter qtconsole |
| F11 | Fullscreen |
| F12 | Terminal panel toggle |

## Run / scripting

| Shortcut | Action |
| --- | --- |
| F5 | Run current file (interpreter from format) |
| Ctrl+Enter | Run selection |
| Ctrl+. | Stop run |
| F6 | **Compile LaTeX → PDF** (auto-picks `xelatex` for fontspec docs) |
| F7 | Run a saved script (picker) |
| Ctrl+Shift+Y | Open Python REPL |
| Ctrl+Alt+R | Notebook: run all cells |
| Ctrl+Alt+↑ / ↓ | Notebook: move cell up / down |

## PDF editing

| Shortcut | Action |
| --- | --- |
| Ctrl+] | Rotate current page 90° CW |
| Ctrl+[ | Rotate current page 90° CCW |
| (menu) | Rotate 180° / Delete current / Extract pages… / Reorder / Insert blank / Merge with PDFs… |

All operations write to a sibling `*-edited.pdf` next to the source.
The original file is never modified.

## Tables / data / sheets

| Shortcut | Action |
| --- | --- |
| F4 | **Switch sheet / table / array / variable / dataset…** — dispatches on active format (XLSX / SQLite / NumPy / MATLAB / HDF5) |
| Ctrl+Shift+Q | **Run SQL…** (SQLite, read-only) |
| Ctrl+Shift+E | Spreadsheet panel (selection stats, edit toggle, charts) |

## LSP

| Shortcut | Action |
| --- | --- |
| F2 | Go to definition |
| Shift+F12 | Find references |
| Ctrl+Shift+H | Show hover info |

## Image / Media

| Shortcut | Action |
| --- | --- |
| R | Rotate image 90° |
| PgUp / PgDn | Previous / next image in folder |
| F9 | Slideshow toggle |
| Ctrl+Alt+S | Save image as |

## Inline LLM

| Shortcut | Action |
| --- | --- |
| Alt+/ | Suggest at cursor |
| Ctrl+J | Toggle chat panel |

## Diff

| Shortcut | Action |
| --- | --- |
| (menu) | Compare with file |
| (menu) | Compare with git HEAD |

## Help

| Shortcut | Action |
| --- | --- |
| Ctrl+? | Keyboard shortcut cheat sheet (auto-generated) |
| (menu) | Documentation… |

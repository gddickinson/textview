# TextView

[![tests](https://github.com/gddickinson/textview/actions/workflows/tests.yml/badge.svg)](https://github.com/gddickinson/textview/actions/workflows/tests.yml)
![last commit](https://img.shields.io/badge/last%20commit-17860ff%20%C2%B7%202026--05--05-blue)
![python](https://img.shields.io/badge/python-3.12-blue)
![PyQt](https://img.shields.io/badge/PyQt-6-41cd52)
![license](https://img.shields.io/badge/license-private-lightgrey)

A modular PyQt6 GUI for viewing text, code, markup, document, image,
video, and tabular files — with live display config, syntax highlighting,
LSP integration, embedded Jupyter notebook + REPL, agent-driven scripting,
and a 302-test regression suite.

![code editor with chat panel](docs/screenshots/03_code_python.png)

See [`INTERFACE.md`](INTERFACE.md) for the navigation map and
[`ROADMAP.md`](ROADMAP.md) for shipped + parked features.

## Showcase

| | |
| --- | --- |
| ![welcome](docs/screenshots/01_welcome.png) **Welcome screen** — quick orientation when the app first opens. | ![CSV in table mode](docs/screenshots/05_csv_table.png) **CSV / TSV** — auto-delimiter, sortable columns, filter bar, selection stats. |
| ![Jupyter notebook](docs/screenshots/08_notebook.png) **Notebooks** — `.ipynb` viewer, editor, and runner with a shared kernel. Cells render rich outputs (HTML / SVG / images / markdown). | ![PDF](docs/screenshots/06_pdf.png) **PDFs** — page-mode rendering via `QPdfView` with link follow-through, search, and copy-as-text. |
| ![Image viewer](docs/screenshots/07_image.png) **Images** — pan / zoom, brightness / contrast / saturation / gamma sliders, eyedropper, crop. Multi-frame WebP / TIFF / GIF. | ![Markdown rendered](docs/screenshots/02_markdown_rendered.png) **Markdown** — rendered HTML view with syntax-highlighted code fences. |
| ![JSON](docs/screenshots/04_json.png) **Structured data** — JSON / YAML / TOML / XML pretty-print + validate via the runner. | ![Dark theme](docs/screenshots/10_dark_theme.png) **Themes** — 10 built-in palettes; switch live without reopening. |

### Unknown-file workflow

When you open a file TextView doesn't natively understand, it identifies
the file by magic bytes / extension / heuristics and shows a markdown
report — then offers to hand off to the chat agent, which can search
for documentation, write a handler script, or (with explicit per-tool
opt-in) install a package and write a plugin to teach the app a new
format.

![unknown file inspector](docs/screenshots/09_unknown_file.png)

See [`docs/unknown-files.md`](docs/unknown-files.md) for the full flow
including the two-gate safety story.

## Install

### conda (recommended on macOS)

The conda env spec pins `sqlite>=3.45` from `conda-forge`, which avoids
the macOS+anaconda `_sqlite3_enable_load_extension` ABI mismatch that
breaks `import sqlite3` (and therefore IPython, ipykernel, the
notebook runner, and the qtconsole).

```bash
conda env create -f environment.yml
conda activate textview
python main.py
```

### pip (Linux / Windows / advanced macOS)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Run the test suite

```bash
python -m pytest                  # full (~9s, 302 cases)
python -m pytest -m "not slow"    # fast subset (skips Jupyter subprocess tests)
python -m pytest tests/test_X.py  # one file
```

## Key shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+P` | Quick open file |
| `Ctrl+Shift+F` | Find in project |
| `Ctrl+F` | Find / replace (regex toggle) |
| `Ctrl+S` | Save |
| `Ctrl+J` | Chat panel |
| `Ctrl+\`` | Terminal |
| `Ctrl+Shift+Y` | Python REPL (uses configured interpreter) |
| `Ctrl+Alt+J` | Jupyter qtconsole |
| `F5` | Run current file (or notebook cell-by-cell) |
| `Ctrl+Alt+R` | Notebook: run all cells |
| `Ctrl+Alt+↑/↓` | Notebook: move cell up / down |
| `F2` | Go to definition (LSP) |
| `Shift+F12` | Find references (LSP) |
| `Ctrl+Shift+H` | Show LSP hover info |
| `Ctrl+;` | Insert snippet |
| `Ctrl+K` | Command palette |

`Run → Choose Python interpreter…` discovers system Pythons, conda envs,
and pyenv versions. Selection persists and is shared across F5,
the Python REPL, qtconsole, and notebook kernel auto-start.

## Dependencies overview

GUI: PyQt6 + PyQt6-WebEngine. Documents: pypdf, python-docx,
mammoth, striprtf, EbookLib, chardet. Charts: matplotlib + numpy.
Images: Pillow. Terminal: pyte. Notebook stack: nbformat,
jupyter_client, ipykernel, qtconsole. LLM (optional, used by chat
panel): anthropic, openai, requests (Ollama). Tests: pytest.

Full pinned list in `environment.yml` (conda) or `requirements.txt` (pip).

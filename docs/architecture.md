# Architecture

A high-level map of the codebase for power users and agents who need
to find their way around.

## Top-level layout

```
text_display/
├── main.py                 entry point
├── environment.yml         conda env
├── requirements.txt        pip mirror
├── pytest.ini              test config
├── INTERFACE.md            navigation map (the canonical reference)
├── ROADMAP.md              shipped + planned features
├── SESSION_LOG.md          append-only history of changes
├── README.md               install + run + key shortcuts
├── docs/                   user + agent documentation (this folder)
├── data/                   bundled file-format database (JSON)
├── src/                    application code (95+ modules, all <500 lines)
├── tests/                  pytest regression suite (826 tests)
├── tools/                  helper scripts (control_client.py, snapshot_matrix.py)
├── plugins/                example plugins
└── sample_files/           tiny sample inputs for trying things out
```

## Core hierarchy

```
QApplication
└── MainWindow (src/app.py)
    ├── TextViewer (src/viewer.py)              [stacked widget]
    │   ├── CodeViewer
    │   ├── QTextBrowser (rendered)               [markdown / archive TOC / cert report / font sheet]
    │   ├── PdfViewer (src/pdf_viewer.py)         [+ annotation mode incl. edit_text]
    │   ├── ImageView (src/image_view.py)
    │   ├── WebView (src/web_view.py)
    │   ├── VideoView (src/video_view.py)         [video + audio with ID3 overlay]
    │   ├── TableView (src/table_view.py)         [CSV / XLSX / SQLite / NumPy / MATLAB / Parquet / HDF5]
    │   ├── NotebookView (src/notebook_view.py)
    │   └── ArchiveView (src/archive_view.py)     [zip / tar / 7z tree + preview]
    ├── docks
    │   ├── ConfigPanel
    │   ├── MetadataPanel
    │   ├── ChatPanel (src/chat_panel.py)
    │   ├── ProjectPanel
    │   ├── ImagePanel
    │   ├── SpreadsheetPanel
    │   ├── DiagnosticsPanel
    │   ├── TerminalDock (src/pty_terminal.py)
    │   └── JupyterDock (src/jupyter_console.py)
    └── controllers
        ├── EditController        edit-mode toggle, save / save-as
        ├── WebController         browser
        ├── RunController         F5 / shell / runner panel
        ├── ImageController       rotate / browse / fit
        ├── ExportController      export-as actions
        ├── BookmarksController   web bookmarks
        ├── RecentFilesController File → recent submenu
        ├── DiskWatcher           live external-change detection
        ├── HookRegistry          ~/.config/TextView/hooks/*.py
        ├── AppAPI                stable façade for plugins / hooks
        ├── PluginRegistry        ~/.config/TextView/plugins/*.py
        ├── LSPController         (src/lsp_controller.py)
        ├── LatexController       (src/latex_controller.py) — F6 PDF compile
        └── ControlServer         (src/control_server.py — opt-in)
```

## Format loaders (extracted-to-CSV table family)

```
file_loader.load_file()
├── csv         → CSV text loaded directly
├── xlsx        → spreadsheet_loader (openpyxl)        F4 sheet picker
├── sqlite      → sqlite_loader (stdlib sqlite3, RO)   F4 table picker + Ctrl+Shift+Q SQL
├── numpy       → numpy_loader                          F4 array picker (.npz)
├── mat         → mat_loader (scipy.io)                F4 variable picker
├── parquet     → parquet_loader (pyarrow)
├── hdf5        → hdf5_loader (h5py / netCDF4)         F4 dataset picker
└── archive     → archive_loader (zip / tar / 7z)      ArchiveView tree
```

## PDF editing pipeline (v3.5, five tiers)

```
PDF menu actions
├── Page ops              → pdf_editor.py (pypdf)
│   rotate / delete / extract / reorder / merge / split / insert blank
├── Annotations           → pdf_annotations.py (PyMuPDF)
│   sticky / freetext / highlight / underline / strikeout / rect / circle / ink
│   - dialog flow        → pdf_annotation_actions.annotate_*
│   - mouse flow         → PdfViewer.set_annotation_mode + bridge
├── Text editing          → pdf_text_edit.py (PyMuPDF redaction)
│   list_text_spans / replace_span / find_and_replace
│   - dialog + find/replace + click-to-edit mode
├── Signing               → pdf_signing.py (pyHanko)
│   sign_pdf (PAdES B-B / B-T) / verify_signatures
└── Reconstruction        → pdf_reconstruct.py
    pdf_to_markdown (pymupdf4llm) / pdf_to_docx (pdf2docx)
```

## Where to find things

- **Open a file** → `MainWindow.open_file` in `src/app.py`. Calls
  `file_loader.load_file` (extension → format) → routes to viewer
  modes via `if fmt == "...": ...`.
- **Toggle render** → `MainWindow.on_toggle_render`.
- **Save** → `EditController.save` (`src/edit_controller.py`).
  Notebook save is intercepted there and routed to
  `notebook_view.save()`.
- **Settings** → `src/settings.py` (`DisplaySettings` dataclass +
  `SettingsManager` with QSettings persistence).
- **Themes** → `src/themes.py`.
- **LLM tools** → `src/llm/tools.py` aggregates from
  `tools_module.py`, `tools_scripts.py`, `tools_memory.py`,
  `tools_docs.py`.
- **Actions** (every `QAction`) → `src/actions.py`.
- **Menus** → `src/menus.py`.

## Conventions

- **500-line cap**: every `src/*.py` file is under 500 lines. When
  one approaches the cap, we extract.
- **`INTERFACE.md`**: read this file BEFORE opening any source — it's
  the navigation map.
- **Tests**: persistent `tests/` directory, 826 cases. Run
  `python -m pytest`. Slow / subprocess tests (~10) are marked
  `@pytest.mark.slow`; CI runs the fast subset on every push.
  Tests for optional-dep modules (.ods, signing, scientific data,
  ML models, etc.) `pytest.skipif` block-style when their dep is
  missing so the suite still passes on a bare host.
- **Append-only log**: `SESSION_LOG.md` records every significant
  change with rationale.
- **Memory store** (Claude-style): `~/.config/TextView/memory/*.md`.
- **Scripts / plugins / hooks**: `~/.config/TextView/{agent_scripts,plugins,hooks}/`.

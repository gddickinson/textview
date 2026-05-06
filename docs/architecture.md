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
├── src/                    application code (50+ modules, all <500 lines)
├── tests/                  pytest regression suite (170+ tests)
├── tools/                  helper scripts (control_client.py)
├── plugins/                example plugins
└── sample_files/           tiny sample inputs for trying things out
```

## Core hierarchy

```
QApplication
└── MainWindow (src/app.py)
    ├── TextViewer (src/viewer.py)              [stacked widget]
    │   ├── CodeViewer
    │   ├── QTextBrowser (rendered)
    │   ├── PdfViewer (src/pdf_viewer.py)
    │   ├── ImageView (src/image_view.py)
    │   ├── WebView (src/web_view.py)
    │   ├── VideoView (src/video_view.py)
    │   ├── TableView (src/table_view.py)
    │   └── NotebookView (src/notebook_view.py)
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
        └── ControlServer         (src/control_server.py — opt-in)
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
- **Tests**: persistent `tests/` directory, 170+ cases. Run
  `python -m pytest`. Slow / subprocess tests are marked
  `@pytest.mark.slow`.
- **Append-only log**: `SESSION_LOG.md` records every significant
  change with rationale.
- **Memory store** (Claude-style): `~/.config/TextView/memory/*.md`.
- **Scripts / plugins / hooks**: `~/.config/TextView/{agent_scripts,plugins,hooks}/`.

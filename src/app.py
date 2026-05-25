"""MainWindow — owns the viewer, docks, menus, status bar, and the
apply-settings / refresh-view orchestration that re-runs on every change."""
import sys; from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QSettings
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QStatusBar, QMessageBox,
    QToolBar, QLabel, QWidget, QVBoxLayout,
)

from .viewer import TextViewer
from .config_panel import ConfigPanel
from .settings import SettingsManager
from .file_loader import (
    load_file, file_info, file_dialog_filter, humansize, DOCUMENT_FORMATS,
    IMAGE_FORMATS, VIDEO_FORMATS, AUDIO_FORMATS, MEDIA_FORMATS, TABLE_FORMATS,
)
from .document_extract import DocumentExtractionError
from .renderers import apply_pygments, render_markdown_html, escape_to_html
from .themes import get_theme
from .pdf_renderer import PdfController
from .rich_doc_controller import RichDocController, RICH_FORMATS
from .latex_controller import (
    LatexController, compile_active_buffer as _latex_compile,
    apply_compiled_pdf as _latex_apply,
)
from .welcome import WELCOME_MARKDOWN
from . import view_styler
from .search_bar import SearchBar
from .edit_controller import EditController
from .view_styler import apply_line_height
from .metadata_panel import MetadataPanel
from .web_controller import WebController
from .run_controller import RunController
from .bookmarks import BookmarksController
from .recent_files import RecentFilesController
from .image_controller import ImageController
from .export_controller import ExportController; from .snippets import SnippetStore
from .lsp_controller import LSPController
from .chat_panel import ChatPanel
from .disk_watcher import DiskWatcher
from .tabs import TabBar
from .project_panel import ProjectPanel
from .image_panel import ImagePanel
from .pty_terminal import TerminalDock
from .table_view import TableFilterBar
from .spreadsheet_panel import SpreadsheetPanel
from .diagnostics_panel import DiagnosticsPanel
from .jupyter_console import JupyterDock; from .citation_panel import CitationPanel, open_at_locator
from .api import AppAPI
from .plugin_loader import PluginRegistry
from .cheat_sheet import show_cheat_sheet
from .command_palette import show_command_palette
from .folder_watcher import FolderWatcher
from .hooks import HookRegistry
from .inline_suggest import InlineSuggester
from .actions import build as _build_actions_into
from .menus import build as _build_menus_into
from . import editor_actions
from . import notebook_actions as _na


class MainWindow(QMainWindow):
    _instances: list = []  # strong refs; entries removed in closeEvent

    @classmethod
    def spawn(cls):
        w = cls(); w.show(); return w

    def __init__(self):
        super().__init__()
        MainWindow._instances.append(self)
        self.setWindowTitle("TextView"); self.resize(1280, 820); self.setAcceptDrops(True)

        self.settings_manager = SettingsManager()
        self.viewer = TextViewer(self)
        self.viewer.code.textChanged.connect(self._on_code_text_changed); self.viewer.code.cursor_paused.connect(self._on_cursor_paused)
        self.viewer.notebook_view.status.connect(lambda m: self.statusBar().showMessage(m, 5000))
        # Surface notebook dirty state through EditController so the standard
        # confirm-discard prompt fires when the user runs cells then tries to
        # close the file or open a different one. Without this, in-memory
        # outputs would be lost silently.
        self.viewer.notebook_view.dirty_changed.connect(self._on_notebook_dirty)
        self.search_bar = SearchBar(self)
        self.tab_bar = TabBar(self)
        self.tab_bar.requested_open.connect(self._on_tab_open); self.tab_bar.requested_clear.connect(self._show_welcome)
        from . import tab_actions as _tab_actions
        self.tab_bar.tab_context_requested.connect(
            lambda idx, p: _tab_actions.show_tab_context_menu(self, idx, p))
        self.table_filter_bar = TableFilterBar(self); self.table_filter_bar.hide()
        self.table_filter_bar.filter_changed.connect(self._on_table_filter_changed)

        container = QWidget(); layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        for w in (self.tab_bar.widget(), self.viewer,
                  self.table_filter_bar, self.search_bar):
            layout.addWidget(w, 1 if w is self.viewer else 0)
        self.setCentralWidget(container)

        R = Qt.DockWidgetArea.RightDockWidgetArea; L = Qt.DockWidgetArea.LeftDockWidgetArea
        self.config_panel = ConfigPanel(self.settings_manager, self); self.config_panel.setObjectName("config_panel"); self.addDockWidget(R, self.config_panel)
        self.metadata_panel = MetadataPanel(self); self.metadata_panel.setObjectName("metadata_panel"); self.addDockWidget(L, self.metadata_panel); self.metadata_panel.hide()
        self.chat_panel = ChatPanel(self); self.chat_panel.setObjectName("chat_panel"); self.addDockWidget(R, self.chat_panel); self.chat_panel.hide(); self.chat_panel.sync_from_settings()
        self.project_panel = ProjectPanel(self); self.project_panel.setObjectName("project_panel"); self.addDockWidget(L, self.project_panel); self.project_panel.hide()
        self.image_panel = ImagePanel(self.viewer.image_view, self); self.addDockWidget(R, self.image_panel); self.image_panel.hide()
        self.viewer.video_view.errored.connect(lambda msg: self.statusBar().showMessage(f"Video error: {msg}", 5000))
        self.terminal_dock = TerminalDock(self); self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock)
        self.terminal_dock.hide(); self.terminal_dock.visibilityChanged.connect(self._on_terminal_visibility)
        self.spreadsheet_panel = SpreadsheetPanel(self.viewer.table_view, self); self.addDockWidget(R, self.spreadsheet_panel); self.spreadsheet_panel.hide()
        self.diagnostics_panel = DiagnosticsPanel(self); self.addDockWidget(R, self.diagnostics_panel); self.diagnostics_panel.hide(); self.diagnostics_panel.jump_requested.connect(self._diag_jump)
        self.jupyter_dock = JupyterDock(self); self.addDockWidget(R, self.jupyter_dock); self.jupyter_dock.hide()
        self.citation_panel = CitationPanel(self); self.addDockWidget(R, self.citation_panel); self.citation_panel.hide(); self.citation_panel.open_requested.connect(lambda p, loc: open_at_locator(self, p, loc))

        self._current_path = None; self._current_content = ""
        self._current_format = "plain"; self._current_encoding = "utf-8"
        self._table_delimiter = ","
        self.viewer.table_view.selection_summary.connect(self._on_table_selection)
        self._pdf, self._rich = PdfController(), RichDocController()
        self._latex = LatexController(self); self._latex.finished.connect(self._on_latex_finished)
        # PDF annotation mode (v3.5 phase 2b) — connects pdf_view's
        # annotation_committed signal to the writer + status-bar.
        from . import pdf_actions as _pdf_actions
        _pdf_actions.attach_annotation_signals(self)
        # PDF inline text editing (v3.5 tier 3) — hooks the same
        # signal for the `edit_text` mode.
        from . import pdf_text_edit_actions as _pdf_text_actions
        _pdf_text_actions.attach_text_edit_signals(self)
        self.edit = EditController(self); self.edit.attach(self.viewer); self.edit.state_changed.connect(self._update_title)
        self.web = WebController(self); self.run = RunController(self); self.bookmarks = BookmarksController(self); self.recent = RecentFilesController(self)
        self.images = ImageController(self); self.exp = ExportController(self); self.snippets = SnippetStore()
        self.lsp = LSPController(self); self.lsp.status.connect(lambda m: self.statusBar().showMessage(m, 4000)); self.lsp.definition_resolved.connect(self._on_definition_resolved); self.lsp.references_resolved.connect(self._on_references_resolved)
        self.disk = DiskWatcher(self); self.folder_watch = FolderWatcher(self)
        self.hooks = HookRegistry(self); self.api = AppAPI(self); self.hooks.load_all(); self.plugins = PluginRegistry(self.api, self)
        self.run.panel.runner.finished.connect(lambda c, s: self.hooks.fire("on_run_finished", c, s))
        self.suggester = InlineSuggester(self)
        self._build_actions(); self._build_menus(); self._build_toolbar(); self._build_statusbar()
        self.settings_manager.changed.connect(self._apply_settings); self._apply_settings()
        self._show_welcome(); self.plugins.load_all()

    def _build_actions(self): _build_actions_into(self)
    def _build_menus(self): _build_menus_into(self)

    def _build_toolbar(self):
        tb = QToolBar("Main"); tb.setObjectName("main_toolbar"); tb.setIconSize(QSize(18, 18)); tb.setMovable(False)
        groups = [
            (self.action_open, self.action_open_url, self.action_save, self.action_reload),
            (self.action_zoom_out, self.action_zoom_in, self.action_zoom_reset),
            (self.action_find, self.action_edit_mode),
            (self.action_toggle_render, self.action_toggle_config),
        ]
        for i, group in enumerate(groups):
            if i: tb.addSeparator()
            for a in group: tb.addAction(a)
        self.addToolBar(tb)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.lbl_file, self.lbl_format = QLabel("No file"), QLabel("")
        self.lbl_encoding, self.lbl_size = QLabel(""), QLabel(""); sb.addWidget(self.lbl_file, 1)
        for w in (self.lbl_format, self.lbl_encoding, self.lbl_size): sb.addPermanentWidget(w)
        self.setStatusBar(sb)

    def _on_table_filter_changed(self, v: int, t: int):
        msg = "" if v == t else f"Filter: {v} of {t} rows match"
        if msg: self.statusBar().showMessage(msg, 5000)
        else:   self.statusBar().clearMessage()

    def _on_table_selection(self, stats: dict):
        if not stats or not stats.get("count"): return
        bits = [f"{stats['count']} cells"]
        if stats.get("numeric"):
            bits += [f"sum {stats['sum']:g}", f"avg {stats['avg']:g}",
                     f"min {stats['min']:g} / max {stats['max']:g}"]
        self.statusBar().showMessage(" · ".join(bits), 6000)

    def _table_copy_tsv(self):
        text = self.viewer.table_view.copy_selection_as_tsv()
        if not text: return
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text); self.statusBar().showMessage("Copied selection as TSV.", 3000)

    def _on_terminal_visibility(self, visible: bool):
        if not visible or self.terminal_dock.term.is_running(): return
        cwd = str(Path(self._current_path).parent) if self._current_path else None
        self.terminal_dock.ensure_started(cwd=cwd)
        # First reveal spawns the shell; thereafter the user uses Restart.
        try: self.terminal_dock.visibilityChanged.disconnect(self._on_terminal_visibility)
        except TypeError: pass

    def _show_welcome(self):
        self._pdf.clear(); self._rich.clear()
        self._current_content, self._current_format = WELCOME_MARKDOWN, "markdown"
        self._current_path, self._current_encoding = None, "utf-8"
        self.setWindowTitle("TextView"); self.lbl_file.setText("Welcome (untitled)")
        self.lbl_format.setText("Format: markdown"); self.lbl_encoding.setText("Encoding: utf-8")
        self.lbl_size.setText(humansize(len(WELCOME_MARKDOWN.encode("utf-8"))))
        self.metadata_panel.update_for(None, None); self.edit.reset()
        self.viewer.code.setPlainText(self._current_content); self.viewer.code.document().clearUndoRedoStacks()
        self.tab_bar.add_or_select(None, "Welcome"); self._refresh_view()

    # ----------------------------------------------------------- File I/O --

    def on_open(self):
        if not self.edit.confirm_discard(): return
        path, _ = QFileDialog.getOpenFileName(self, "Open file", "", file_dialog_filter())
        if path: self.open_file(path, confirm=False)

    def open_file(self, path, *, confirm: bool = True):
        # Every entry point that switches the current buffer must check for
        # unsaved changes. Callers that already prompted (Open dialog, tab
        # switch, disk-reload prompt) pass confirm=False to avoid double-asking.
        if confirm and not self.edit.confirm_discard(): return
        # Security scan + open-time confirmation. Returns 'open' if the
        # file is clean / the user accepted, 'quarantine' if the file was
        # moved (we then bail), or 'cancel'.
        try:
            from .security_dialog import evaluate_open
            decision = evaluate_open(self, path)
        except Exception: decision = "open"
        if decision != "open": return
        try:
            content, encoding, fmt = load_file(path)
        except FileNotFoundError:
            QMessageBox.critical(self, "Open failed", f"File not found:\n{path}"); return
        except DocumentExtractionError as e:
            QMessageBox.critical(self, "Extraction failed", str(e)); return
        except Exception as e:
            QMessageBox.critical(self, "Open failed", f"Could not open file:\n{e}"); return

        self._current_path, self._current_content = path, content
        self._current_format, self._current_encoding = fmt, encoding
        self._pdf.clear(); self._rich.clear(); self._latex.clear(); self.viewer.video_view.teardown()
        if fmt == "pdf":
            self._pdf.load(path)
        elif fmt in RICH_FORMATS:
            self._rich.load(path, fmt)
        elif fmt in IMAGE_FORMATS:
            self.viewer.image_view.load(path)
        elif fmt in MEDIA_FORMATS:
            self.viewer.video_view.load(path)
        elif fmt in TABLE_FORMATS:
            self._table_source = None; self._load_csv_table(content)
            if fmt == "xlsx":
                from .spreadsheet_loader import list_sheets
                try:
                    self._xlsx_sheets = list_sheets(path)
                except Exception:
                    self._xlsx_sheets = []
                self._xlsx_sheet_index = 0
            elif fmt == "sqlite":
                from .sqlite_loader import list_tables
                try:
                    self._sqlite_tables = list_tables(path)
                except Exception:
                    self._sqlite_tables = []
                self._sqlite_table_index = 0
            elif fmt == "numpy":
                from .numpy_loader import list_arrays
                try:
                    self._numpy_arrays = list_arrays(path)
                except Exception:
                    self._numpy_arrays = []
                self._numpy_array_index = 0
            elif fmt == "mat":
                from .mat_loader import list_variables
                try:
                    self._mat_variables = list_variables(path)
                except Exception:
                    self._mat_variables = []
                self._mat_variable_index = 0
            elif fmt == "hdf5":
                from .hdf5_loader import list_datasets
                try:
                    self._hdf5_datasets = list_datasets(path)
                except Exception:
                    self._hdf5_datasets = []
                self._hdf5_dataset_index = 0
        elif fmt == "notebook":
            self.viewer.notebook_view.load(path)
        elif fmt == "archive":
            from .archive_loader import list_members
            try:
                self._archive_members = list_members(path)
            except Exception:
                self._archive_members = []
            # Load into the dedicated tree view as the default; Ctrl+T
            # flips to the markdown-TOC rendered view.
            self.viewer.archive_view.load(path)
        elif fmt == "mesh":
            # Dedicated 3D mesh viewer with embedded matplotlib canvas.
            self.viewer.mesh_view.load(path)
        elif fmt == "plain":
            from .file_inspector import maybe_unknown_file_report
            if (rep := maybe_unknown_file_report(path)) is not None: content, kind = rep; self._current_content = content; self._current_format = fmt = "markdown"; self.lbl_format.setText(f"Format: {kind}")
        self.viewer.rendered.setSearchPaths([str(Path(path).parent)])

        info = file_info(path)
        self.lbl_file.setText(info["name"]); self.lbl_format.setText(f"Format: {fmt}"); self.lbl_encoding.setText(f"Encoding: {encoding}")
        # Mirror content into buffer before _refresh_view (else stale).
        self.edit.reset()
        self.viewer.code.setPlainText(self._current_content); self.viewer.code.document().clearUndoRedoStacks()
        self._refresh_view(); self._update_title(); self.metadata_panel.update_for(path, fmt)
        self.recent.add(path); editor_actions.update_counts(self); self.disk.watch(path)
        self.tab_bar.add_or_select(path, info["name"])
        self.hooks.fire("on_file_opened", path); self.lsp.on_file_opened(path, fmt, content)
        self.statusBar().showMessage(f"Opened {info['name']}", 3000)

    def on_reload(self):
        if self._current_path:
            self.open_file(self._current_path)

    def _on_tab_open(self, path: str):
        if path != self._current_path and self.edit.confirm_discard():
            self.open_file(path, confirm=False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).is_file():
                self.open_file(url.toLocalFile())
                event.acceptProposedAction(); return
        event.ignore()

    def _apply_settings(self):
        d = self.settings_manager.display
        view_styler.apply_all(self.viewer, d, get_theme(d.theme), self._current_format)
        self.web.apply_settings(d); self.run.apply_settings(d)
        self.lsp.set_enabled(d.lsp_enabled); self.viewer.code.set_hover_pause_enabled(d.lsp_enabled and d.lsp_hover_on_pause); self.viewer.notebook_view.set_default_interpreter(d.python_interpreter or sys.executable)
        self._refresh_view()

    def _on_code_text_changed(self):
        if self._current_path and self.edit.editing: self.lsp.on_text_changed(self._current_path, self.viewer.code.toPlainText())

    def _on_notebook_dirty(self, on: bool):
        # Mirror notebook dirty state into EditController so confirm_discard
        # picks up unsaved cell edits / outputs when the user navigates away.
        if self._current_format != "notebook": return
        self.edit.modified = bool(on); self.edit.state_changed.emit()

    def _lsp_hover_at_cursor(self): self._lsp_hover_for(self.viewer.code.textCursor())
    def _on_cursor_paused(self, p): self._lsp_hover_for(self.viewer.code.cursorForPosition(p))
    def _lsp_hover_for(self, cursor):
        if self._current_path: self.lsp.request_hover(self._current_path, cursor.blockNumber(), cursor.positionInBlock())

    def open_python_repl(self):              _na.open_python_repl(self)
    def pick_python_interpreter(self):        _na.pick_python_interpreter(self)
    def open_jupyter_console(self):           _na.open_jupyter_console(self)
    def notebook_start_kernel(self):          _na.notebook_start_kernel(self)
    def notebook_run_all(self):               _na.notebook_run_all(self)
    def notebook_add_cell(self, kind):        _na.notebook_add_cell(self, kind)
    def notebook_delete_current(self):        _na.notebook_delete_current(self)
    def notebook_change_type(self, k):        _na.notebook_change_type(self, k)
    def notebook_move(self, d):               _na.notebook_move(self, d)

    def _lsp_pos(self):
        c = self.viewer.code.textCursor()
        return (self._current_path, c.blockNumber(), c.positionInBlock()) if self._current_path else None
    def lsp_goto_definition(self): p = self._lsp_pos();  p and self.lsp.request_definition(*p)
    def lsp_find_references(self): p = self._lsp_pos();  p and self.lsp.request_references(*p)
    def _on_references_resolved(self, locs): from .lsp_controller import show_references_dialog as f; f(self, locs)
    def _on_definition_resolved(self, p, l, c): from .lsp_controller import jump_to_definition as f; f(self, p, l, c)
    def _diag_jump(self, line, char):
        if self._current_path: self._on_definition_resolved(self._current_path, line, char)

    def _sync_content(self):
        m = self.viewer.mode()
        if m == self.viewer.MODE_CODE:
            self._current_content = self.viewer.code.toPlainText()
        elif (m == self.viewer.MODE_TABLE and self._current_format in TABLE_FORMATS
                and self.viewer.table_view.has_model()):
            text = self.viewer.table_view.serialize(self._table_delimiter)
            self._current_content = text
            self._table_source = text  # in sync; skip spurious reload below

    def _load_csv_table(self, content):
        if content == getattr(self, "_table_source", None): return
        d = self.settings_manager.display
        self._table_delimiter = self.viewer.table_view.load(
            content, has_header=d.table_show_header,
            delimiter=d.table_delimiter or None)
        self._table_source = content
        self.table_filter_bar.attach(self.viewer.table_view)
        self.spreadsheet_panel.refresh_for_model()

    def _populate_code_view(self):
        d = self.settings_manager.display; theme = get_theme(d.theme)
        self.viewer.code.setPlainText(self._current_content); apply_line_height(self.viewer.code, d.line_height)
        fmt = self._current_format
        # Skip Pygments on large files (>250KB) — full-buffer token-walking blocks the UI for seconds.
        if d.syntax_highlight and len(self._current_content or "") <= 250_000 and fmt not in ("plain",) and fmt not in DOCUMENT_FORMATS:
            apply_pygments(self.viewer.code, self._current_content, self._current_path, theme["pygments_style"], fmt)
        self.viewer.code.document().clearUndoRedoStacks()

    def _refresh_view(self):
        d = self.settings_manager.display
        theme = get_theme(d.theme)
        fmt = self._current_format
        if fmt == "web": self.viewer.show_web(); return
        if fmt == "notebook":
            self.viewer.show_notebook(); self.lbl_format.setText("Notebook"); return
        if fmt == "archive":
            self.viewer.show_archive()
            n = len(getattr(self, "_archive_members", []) or [])
            self.lbl_format.setText(
                f"Archive · {n} members · "
                f"{Path(self._current_path or '').name}")
            return
        if fmt == "mesh":
            self.viewer.show_mesh()
            self.lbl_format.setText(
                f"3D mesh · {Path(self._current_path or '').name}")
            return
        if fmt in MEDIA_FORMATS:
            self.viewer.show_video()
            label = "Audio" if fmt in AUDIO_FORMATS else "Video"
            self.lbl_format.setText(
                f"{label} · {Path(self._current_path or '').name}")
            return
        if fmt in IMAGE_FORMATS:
            if d.image_checkered_background:
                self.viewer.image_view.set_checkered(True)
            else:
                self.viewer.image_view.set_background(theme["bg"])
            self.viewer.show_image()
            self.lbl_format.setText(f"Image · {self.viewer.image_view.info()}")
            return
        if fmt == "pdf" and d.pdf_render_mode == "rendered" and self._pdf.doc:
            self._pdf.attach(
                self.viewer.pdf_view, d.pdf_page_mode, d.pdf_zoom_mode, d.pdf_zoom,
            )
            self.viewer.show_pdf()
            return
        if fmt in TABLE_FORMATS and d.csv_view_as_table and self.viewer.table_view.has_model():
            self._sync_content()  # pull live edits before deciding to re-parse
            self._load_csv_table(self._current_content)
            view_styler.apply_table(self.viewer.table_view, d)
            self.viewer.show_table()
            self.table_filter_bar.show()
            suffix = ""
            if fmt == "xlsx":
                sheets = getattr(self, "_xlsx_sheets", []) or []
                idx = getattr(self, "_xlsx_sheet_index", 0)
                if 0 <= idx < len(sheets):
                    suffix = f" · sheet {idx + 1}/{len(sheets)}: {sheets[idx]!r}"
            elif fmt == "sqlite":
                tables = getattr(self, "_sqlite_tables", []) or []
                idx = getattr(self, "_sqlite_table_index", 0)
                if 0 <= idx < len(tables):
                    suffix = f" · table {idx + 1}/{len(tables)}: {tables[idx]!r}"
            elif fmt == "numpy":
                arrays = getattr(self, "_numpy_arrays", []) or []
                idx = getattr(self, "_numpy_array_index", 0)
                if 0 <= idx < len(arrays):
                    suffix = f" · array {idx + 1}/{len(arrays)}: {arrays[idx]!r}"
            elif fmt == "mat":
                vars_ = getattr(self, "_mat_variables", []) or []
                idx = getattr(self, "_mat_variable_index", 0)
                if 0 <= idx < len(vars_):
                    suffix = f" · variable {idx + 1}/{len(vars_)}: {vars_[idx]!r}"
            elif fmt == "hdf5":
                ds = getattr(self, "_hdf5_datasets", []) or []
                idx = getattr(self, "_hdf5_dataset_index", 0)
                if 0 <= idx < len(ds):
                    suffix = f" · dataset {idx + 1}/{len(ds)}: {ds[idx]!r}"
            self.lbl_format.setText(
                f"Table · {self.viewer.table_view.shape_label()} · "
                f"sep={self._table_delimiter!r}{suffix}")
            return
        self.table_filter_bar.hide()

        # In edit mode, leave the document alone so ticks preserve edits + undo.
        if self.edit.editing:
            self.viewer.show_code()
            return

        # Pull live edits into _current_content before re-rendering.
        self._sync_content()

        if d.render_markdown:
            if fmt in ("markdown", "archive", "cert", "blend"):
                self.viewer.rendered.setHtml(render_markdown_html(self._current_content, theme, d))
                self.viewer.show_rendered(); return
            if fmt == "html" or fmt == "font":
                self.viewer.rendered.setHtml(self._current_content)
                self.viewer.show_rendered(); return
            if fmt in RICH_FORMATS and self._rich.has_body():
                self.viewer.rendered.setHtml(self._rich.render(theme, d))
                self.viewer.show_rendered(); return

        self._populate_code_view()
        self.viewer.show_code()

    def on_toggle_render(self):
        d = self.settings_manager.display; theme = get_theme(d.theme); self._sync_content()
        if self._current_format in IMAGE_FORMATS or self._current_format in MEDIA_FORMATS or self._current_format == "notebook": return  # no source/rendered split
        if self._current_format == "archive":
            if self.viewer.mode() == self.viewer.MODE_ARCHIVE:
                # Flip to markdown TOC.
                self.viewer.rendered.setHtml(
                    render_markdown_html(self._current_content, theme, d))
                self.viewer.show_rendered()
            else:
                self.viewer.show_archive()
            return
        if self._current_format == "latex":
            if self.viewer.mode() == self.viewer.MODE_PDF and self._pdf.doc:
                self._populate_code_view(); self.viewer.show_code()
            else:
                self.compile_latex()
            return
        if self._current_format == "pdf" and self._pdf.doc:
            if self.viewer.mode() == self.viewer.MODE_PDF:
                self._populate_code_view(); self.viewer.show_code()
            else:
                self._pdf.attach(self.viewer.pdf_view, d.pdf_page_mode,
                                 d.pdf_zoom_mode, d.pdf_zoom)
                self.viewer.show_pdf()
            return
        if self._current_format in TABLE_FORMATS and self.viewer.table_view.has_model():
            if self.viewer.mode() == self.viewer.MODE_TABLE:
                self._populate_code_view(); self.viewer.show_code()
                self.table_filter_bar.hide()
            else:
                self._load_csv_table(self._current_content)
                view_styler.apply_table(self.viewer.table_view, d)
                self.viewer.show_table()
                self.table_filter_bar.show()
            return
        if self.viewer.mode() == self.viewer.MODE_RENDERED:
            self._populate_code_view()
            self.viewer.show_code()
            return
        if self._current_format in ("markdown", "archive", "cert", "blend"):
            self.viewer.rendered.setHtml(
                render_markdown_html(self._current_content, theme, d)
            )
        elif self._current_format == "html" or self._current_format == "font":
            self.viewer.rendered.setHtml(self._current_content)
        elif self._current_format in RICH_FORMATS and self._rich.has_body():
            self.viewer.rendered.setHtml(self._rich.render(theme, d))
        else:
            self.viewer.rendered.setHtml(escape_to_html(self._current_content, theme))
        self.viewer.show_rendered()

    def compile_latex(self): _latex_compile(self)
    def _on_latex_finished(self, ok, pdf_path, message): _latex_apply(self, ok, pdf_path, message)

    def _zoom(self, direction):
        m, v = self.viewer.mode(), self.viewer
        if m == v.MODE_IMAGE:
            (v.image_view.zoom_in if direction > 0 else v.image_view.zoom_out)()
            self.lbl_format.setText(f"Image · {v.image_view.info()}")
        elif m == v.MODE_WEB:
            (v.web_view.zoom_in if direction > 0 else v.web_view.zoom_out)()
        else:
            d = self.settings_manager.display
            new = max(6, min(96, d.font_size + direction))
            if new != d.font_size:
                self.settings_manager.update("font_size", new)
                self.config_panel._sync_from_settings()

    def _zoom_reset(self):
        m, v = self.viewer.mode(), self.viewer
        if m == v.MODE_IMAGE:
            v.image_view.fit_to_window()
            self.lbl_format.setText(f"Image · {v.image_view.info()}")
        elif m == v.MODE_WEB:
            v.web_view.zoom_reset(self.settings_manager.display.web_default_zoom)
        else:
            self.settings_manager.update("font_size", 14)
            self.config_panel._sync_from_settings()

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()


    # ----------------------------------------------------------- Browser ---

    def on_open_url(self):
        self.web.open_dialog()

    def open_url(self, url: str):
        self.web.load(url)

    # ----------------------------------------------- Search / Edit / Title --

    def on_find(self):
        from PyQt6.QtWidgets import QInputDialog
        m = self.viewer.mode()
        if m == self.viewer.MODE_PDF:
            text, ok = QInputDialog.getText(self, "Find in PDF", "Text to find:")
            if ok and text:
                n = self.viewer.pdf_view.find(text)
                self.statusBar().showMessage(
                    f"{n} match{'es' if n != 1 else ''} for {text!r}", 5000,
                )
            return
        if m == self.viewer.MODE_WEB:
            text, ok = QInputDialog.getText(self, "Find in page", "Text to find:")
            if ok and text:
                self.viewer.web_view.find_text(text)
            return
        self.search_bar.attach(self.viewer.active_widget())
        self.search_bar.set_replace_enabled(self.edit.editing)
        self.search_bar.show_and_focus()

    def on_toggle_edit(self):
        self.edit.toggle_editing()
        self.search_bar.set_replace_enabled(self.edit.editing)

    def _update_title(self):
        name = Path(self._current_path).name if self._current_path else "untitled"
        title = f"TextView — {name}"
        if self.edit.modified:
            title = "● " + title
        if self.edit.editing:
            title += " [edit]"
        self.setWindowTitle(title)

    def closeEvent(self, event):
        if not self.edit.confirm_discard():
            event.ignore(); return
        try: self.terminal_dock.term.kill()
        except Exception: pass
        # Only the last window persists workspace — secondaries don't clobber it.
        if len(MainWindow._instances) <= 1:
            self.tab_bar.save_session(); s = QSettings(); s.setValue("workspace/geometry", self.saveGeometry()); s.setValue("workspace/state", self.saveState())
        try: MainWindow._instances.remove(self)
        except ValueError: pass
        event.accept()

    def restore_workspace(self):
        s = QSettings(); g = s.value("workspace/geometry"); st = s.value("workspace/state")
        if g is not None: self.restoreGeometry(g)
        if st is not None: self.restoreState(st)

    def restore_tabs(self):
        self.tab_bar.restore_into(self)

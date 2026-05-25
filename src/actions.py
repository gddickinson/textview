"""Centralized action wiring for MainWindow.

Pulled out of `app.py` to keep that file under the 500-line cap. Each
attribute set on the window is a `QAction`; the `_build_actions` helper
mostly just enumerates them.
"""
from PyQt6.QtGui import QAction, QKeySequence

from . import editor_actions
from .cheat_sheet import show_cheat_sheet
from .command_palette import show_command_palette
from .quick_open import show_quick_open
from .diff_view import compare_with_file, compare_with_git_head
from .folder_watcher import show_watch_dialog
from .hooks import write_example as hook_write_example


def make_action(window, text, slot, shortcut=None):
    a = QAction(text, window)
    if shortcut is not None: a.setShortcut(shortcut)
    a.triggered.connect(slot); return a


def dock_action(dock, text, sc):
    a = dock.toggleViewAction(); a.setText(text); a.setShortcut(sc); return a


def build(w):
    """Attach every QAction to `w` (MainWindow). Returns nothing —
    actions are stored as `w.action_*` attributes for menu/toolbar use."""
    mk = lambda *a: make_action(w, *a)
    SK = QKeySequence.StandardKey

    w.action_open = mk("Open…", w.on_open, SK.Open)
    w.action_new_tab = mk("New tab", w._show_welcome, "Ctrl+N")
    from .templates_dialog import show_new_from_template as _show_new_from_template
    w.action_new_from_template = mk(
        "New from template…",
        lambda: _show_new_from_template(w), "Ctrl+Alt+N",
    )
    from .app import MainWindow
    w.action_new_window = mk("New window", lambda: MainWindow.spawn(), "Ctrl+Shift+N")
    w.action_reload = mk("Reload", w.on_reload, "Ctrl+R")
    w.action_close_file = mk("Close file", w._show_welcome, "Ctrl+W")
    w.action_close_all = mk("Close all tabs", w.tab_bar.close_all, "Ctrl+Shift+Alt+W")
    from . import tab_actions as _tab_actions
    w.action_detach_tab = mk("Detach tab to new window",
                             lambda: _tab_actions.detach_current_tab(w),
                             "Ctrl+Shift+T")
    w.action_export_html = mk("Export as HTML…", w.exp.html)
    w.action_export_pdf = mk("Export as PDF…", w.exp.pdf)
    w.action_export_md = mk("Export as Markdown…", w.exp.md)
    w.action_export_txt = mk("Export as Plain Text…", w.exp.txt)
    w.action_export_rtf = mk("Export as RTF…", w.exp.rtf)
    w.action_export_png = mk("Export as PNG snapshot…", w.exp.png)
    w.action_print = mk("Print…", w.exp.print_, SK.Print)
    w.action_copy_all = mk("Copy all", w.exp.copy_all, "Ctrl+Shift+C")
    w.action_quit = mk("Quit", w.close, SK.Quit)
    w.action_toggle_render = mk("Toggle rendered view", w.on_toggle_render, "Ctrl+T")
    w.action_zoom_in = mk("Zoom in", lambda: w._zoom(+1), SK.ZoomIn)
    w.action_zoom_out = mk("Zoom out", lambda: w._zoom(-1), SK.ZoomOut)
    w.action_zoom_reset = mk("Reset zoom", w._zoom_reset, "Ctrl+0")
    w.action_find = mk("Find / Replace…", w.on_find, SK.Find)
    w.action_edit_mode = mk("Edit mode", w.on_toggle_edit, "Ctrl+E")
    w.action_save = mk("Save", w.edit.save, SK.Save)
    w.action_save_as = mk("Save as…", w.edit.save_as, SK.SaveAs)
    w.action_undo = mk("Undo", lambda: w.viewer.code.undo(), SK.Undo)
    w.action_redo = mk("Redo", lambda: w.viewer.code.redo(), SK.Redo)
    w.action_open_url = mk("Open URL…", w.on_open_url, "Ctrl+L")
    w.action_home = mk("Home page", w.web.go_home, "Ctrl+Home")
    w.action_bookmark = mk("Bookmark this page", w.bookmarks.add_current, "Ctrl+D")
    w.action_compile_latex = mk("Compile LaTeX → PDF", w.compile_latex, "F6")
    # PDF page operations — all write to a sibling `name-edited.pdf`,
    # never mutate the source. Open the result in a new tab.
    from . import pdf_actions as _pdf
    w.action_pdf_rotate_cw    = mk("Rotate current page 90° CW",  lambda: _pdf.rotate_current_page(w, 90),  "Ctrl+]")
    w.action_pdf_rotate_ccw   = mk("Rotate current page 90° CCW", lambda: _pdf.rotate_current_page(w, 270), "Ctrl+[")
    w.action_pdf_rotate_180   = mk("Rotate current page 180°",    lambda: _pdf.rotate_current_page(w, 180))
    w.action_pdf_delete_page  = mk("Delete current page…",        lambda: _pdf.delete_current_page(w))
    w.action_pdf_extract      = mk("Extract pages…",              lambda: _pdf.extract_pages_dialog(w))
    w.action_pdf_merge        = mk("Merge with PDFs…",            lambda: _pdf.merge_with_dialog(w))
    w.action_pdf_insert_after = mk("Insert blank page after current", lambda: _pdf.insert_blank_after_current(w))
    w.action_pdf_insert_start = mk("Insert blank page at start",      lambda: _pdf.insert_blank_at_start(w))
    w.action_pdf_reorder      = mk("Reorder pages…",              lambda: _pdf.reorder_pages_dialog(w))
    # Annotations (v3.5 phase 2a — dialog-driven; phase 2b adds mouse UX).
    w.action_pdf_annot_sticky  = mk("Annotate: sticky note…",      lambda: _pdf.annotate_sticky_note(w))
    w.action_pdf_annot_text    = mk("Annotate: free-text box…",    lambda: _pdf.annotate_freetext(w))
    w.action_pdf_annot_hl      = mk("Annotate: highlight rect…",   lambda: _pdf.annotate_highlight(w))
    w.action_pdf_annot_rect    = mk("Annotate: rectangle…",        lambda: _pdf.annotate_rectangle(w))
    w.action_pdf_annot_circle  = mk("Annotate: circle / ellipse…", lambda: _pdf.annotate_circle(w))
    w.action_pdf_annot_list    = mk("Annotations: list…",          lambda: _pdf.show_annotations_dialog(w))
    w.action_pdf_annot_del_one = mk("Annotations: delete one…",    lambda: _pdf.delete_annotation_dialog(w))
    w.action_pdf_annot_clear   = mk("Annotations: clear all…",     lambda: _pdf.clear_annotations_action(w))
    from .archive_loader import (
        show_extract_member_picker as _arc_pick,
        show_extract_all as _arc_all,
    )
    w.action_archive_extract_one = mk("Archive: extract member…",
                                       lambda: _arc_pick(w))
    w.action_archive_extract_all = mk("Archive: extract all…",
                                       lambda: _arc_all(w))
    w.action_run = mk("Run", w.run.run_current, "F5")
    w.action_run_selection = mk("Run selection", w.run.run_selection, "Ctrl+Return")
    w.action_stop_run = mk("Stop", w.run.stop, "Ctrl+.")
    w.action_toggle_runner = w.run.toggle_action()
    w.action_goto_line = mk("Go to line…", lambda: editor_actions.goto_line(w), "Ctrl+G")
    w.action_toggle_comment = mk("Toggle comment", lambda: editor_actions.toggle_line_comment(w), "Ctrl+/")
    w.action_move_line_up = mk("Move line up", lambda: w.viewer.code.move_line(-1), "Alt+Up")
    w.action_move_line_down = mk("Move line down", lambda: w.viewer.code.move_line(+1), "Alt+Down")
    w.action_dup_line = mk("Duplicate line", lambda: w.viewer.code.duplicate_line(), "Ctrl+Shift+D")
    w.action_select_line = mk("Select line", lambda: w.viewer.code.select_line(), "Ctrl+Shift+L")
    w.action_toggle_folding = mk("Toggle code folding",
        lambda: w.viewer.code.fold.set_enabled(not w.viewer.code.fold.enabled))
    from .snippets import show_snippet_picker, save_selection_as_snippet
    w.action_insert_snippet = mk("Insert snippet…",
        lambda: show_snippet_picker(w), "Ctrl+;")
    w.action_save_snippet = mk("Save selection as snippet…",
        lambda: save_selection_as_snippet(w))
    w.action_lsp_hover = mk("Show LSP hover info", w._lsp_hover_at_cursor, "Ctrl+Shift+H")
    w.action_lsp_goto_def = mk("Go to definition (LSP)", w.lsp_goto_definition, "F2")
    w.action_lsp_find_refs = mk("Find references (LSP)", w.lsp_find_references, "Shift+F12")
    # Help menu — open bundled docs as in-app tabs.
    from pathlib import Path as _P
    _DOCS = _P(__file__).resolve().parent.parent / "docs"
    def _opendoc(stem):
        def _f(): w.open_file(str(_DOCS / f"{stem}.md"))
        return _f
    w.action_docs_index    = mk("Documentation…",         _opendoc("INDEX"))
    w.action_docs_overview = mk("Overview",               _opendoc("overview"))
    w.action_docs_workspace = mk("Workspace RAG",          _opendoc("workspace-rag"))
    w.action_docs_unknown  = mk("Unknown files",          _opendoc("unknown-files"))
    w.action_docs_security = mk("Security & sandboxing",  _opendoc("security"))
    from .format_db_dialog import show_format_db
    w.action_format_db = mk("File formats database…",
                            lambda: show_format_db(w), "Ctrl+Shift+B")
    from .security_dialog import show_security_report, show_quarantine_browser
    w.action_security_report = mk("Security report…",
                                   lambda: show_security_report(w),
                                   "F8")
    w.action_quarantine_browser = mk("Quarantined files…",
                                      lambda: show_quarantine_browser(w))
    w.action_docs_formats  = mk("File formats",           _opendoc("file-formats"))
    w.action_docs_shortcuts = mk("Keyboard reference",    _opendoc("shortcuts"))
    w.action_docs_notebook = mk("Notebook guide",         _opendoc("notebook"))
    w.action_docs_lsp      = mk("LSP / language servers", _opendoc("lsp"))
    w.action_docs_chat     = mk("Chat / LLM",             _opendoc("chat"))
    w.action_docs_scripts  = mk("Agent scripts",          _opendoc("scripts"))
    w.action_docs_plugins  = mk("Plugins",                _opendoc("plugins"))
    w.action_docs_hooks    = mk("Hooks",                  _opendoc("hooks"))
    w.action_docs_agent_api = mk("Agent / LLM tool API",  _opendoc("agent-api"))
    w.action_docs_control  = mk("External control server", _opendoc("control-server"))
    w.action_docs_arch     = mk("Architecture (code map)", _opendoc("architecture"))
    w.action_docs_trouble  = mk("Troubleshooting",        _opendoc("troubleshooting"))
    w.action_to_spaces = mk("Convert to spaces", lambda: editor_actions.convert_indentation(w, True))
    w.action_to_tabs = mk("Convert to tabs", lambda: editor_actions.convert_indentation(w, False))
    w.action_le_lf = mk("Line endings → LF", lambda: editor_actions.convert_line_endings(w, "lf"))
    w.action_le_crlf = mk("Line endings → CRLF", lambda: editor_actions.convert_line_endings(w, "crlf"))
    w.action_fullscreen = mk("Fullscreen", w._toggle_fullscreen, "F11")
    w.action_image_rotate = mk("Rotate image 90°", lambda: w.images.rotate(90), "R")
    w.action_image_next = mk("Next image in folder", lambda: w.images.step_in_folder(1), "PgDown")
    w.action_image_prev = mk("Previous image in folder", lambda: w.images.step_in_folder(-1), "PgUp")
    w.action_slideshow = mk("Toggle slideshow", lambda: w.images.toggle_slideshow(3000), "F9")
    w.action_image_save_as = mk("Save image as…", w.images.save_as, "Ctrl+Alt+S")
    w.action_view_source = mk("View page source", w.web.view_source, "Ctrl+U")
    w.action_devtools = mk("Developer tools", w.web.open_devtools, "Ctrl+Shift+I")
    w.action_reading_mode = mk("Reading mode", w.web.reading_mode, "Ctrl+Shift+R")
    w.action_open_folder = mk("Open folder…", w.project_panel.open_dialog, "Ctrl+Shift+O")
    w.action_cheat_sheet = mk("Keyboard shortcuts", lambda: show_cheat_sheet(w), "Ctrl+?")
    w.action_command_palette = mk("Run command", lambda: show_command_palette(w), "Ctrl+K")
    w.action_quick_open = mk("Quick open file…", lambda: show_quick_open(w), "Ctrl+P")
    from .workspace_search import show_workspace_search
    w.action_workspace_search = mk("Find in project…",
        lambda: show_workspace_search(w), "Ctrl+Shift+F")
    w.action_compare_file = mk("Compare with file…", lambda: compare_with_file(w))
    w.action_compare_git = mk("Compare with git HEAD", lambda: compare_with_git_head(w))
    w.action_inline_suggest = mk("Suggest at cursor", w.suggester.request, "Alt+/")
    w.action_python_repl = mk("Open Python REPL", w.open_python_repl, "Ctrl+Shift+Y")
    w.action_pick_python = mk("Choose Python interpreter…", w.pick_python_interpreter)
    w.action_jupyter_console = mk("Open Jupyter console", w.open_jupyter_console, "Ctrl+Alt+J")
    w.action_notebook_start = mk("Notebook: start kernel", w.notebook_start_kernel)
    w.action_notebook_run_all = mk("Notebook: run all cells", w.notebook_run_all, "Ctrl+Alt+R")
    w.action_notebook_add_code = mk("Notebook: add code cell below", lambda: w.notebook_add_cell("code"))
    w.action_notebook_add_md = mk("Notebook: add markdown cell below", lambda: w.notebook_add_cell("markdown"))
    w.action_notebook_delete = mk("Notebook: delete current cell", w.notebook_delete_current)
    w.action_notebook_to_code = mk("Notebook: change cell to code", lambda: w.notebook_change_type("code"))
    w.action_notebook_to_md = mk("Notebook: change cell to markdown", lambda: w.notebook_change_type("markdown"))
    w.action_notebook_move_up = mk("Notebook: move cell up", lambda: w.notebook_move(-1), "Ctrl+Alt+Up")
    w.action_notebook_move_down = mk("Notebook: move cell down", lambda: w.notebook_move(+1), "Ctrl+Alt+Down")
    w.action_watch_folder = mk("Watch folder…", lambda: show_watch_dialog(w), "Ctrl+Shift+W")
    w.action_reload_hooks = mk("Reload scripting hooks", w.hooks.reload)
    w.action_hooks_dir = mk("Show hooks folder", lambda: hook_write_example(w))
    w.action_toggle_config = dock_action(w.config_panel, "Configuration panel", "Ctrl+,")
    w.action_toggle_metadata = dock_action(w.metadata_panel, "Metadata panel", "Ctrl+I")
    w.action_toggle_chat = dock_action(w.chat_panel, "Chat panel", "Ctrl+J")
    w.action_toggle_project = dock_action(w.project_panel, "Project panel", "Ctrl+Shift+P")
    w.action_toggle_image_panel = dock_action(w.image_panel, "Image adjustments panel", "Ctrl+Shift+M")
    w.action_toggle_terminal = dock_action(w.terminal_dock, "Shell terminal", "Ctrl+`")
    w.action_table_copy_tsv = mk("Copy table selection as TSV", w._table_copy_tsv)

    def _switch_sheet_or_table():
        fmt = w._current_format
        if fmt == "xlsx":
            from .spreadsheet_loader import show_sheet_picker; show_sheet_picker(w)
        elif fmt == "sqlite":
            from .sqlite_loader import show_table_picker; show_table_picker(w)
        elif fmt == "numpy":
            from .numpy_loader import show_array_picker; show_array_picker(w)
        elif fmt == "mat":
            from .mat_loader import show_variable_picker; show_variable_picker(w)
        elif fmt == "hdf5":
            from .hdf5_loader import show_dataset_picker; show_dataset_picker(w)
        else:
            w.statusBar().showMessage(
                "Switch: not a workbook, database, or scientific data file.", 5000)
    w.action_switch_sheet = mk("Switch sheet / table / array / variable…",
                               _switch_sheet_or_table, "F4")
    from .sqlite_loader import show_query_runner as _show_query_runner
    w.action_run_sql = mk("Run SQL (SQLite)…",
                         lambda: _show_query_runner(w), "Ctrl+Shift+Q")
    w.action_toggle_spreadsheet = dock_action(w.spreadsheet_panel, "Spreadsheet panel", "Ctrl+Shift+E")
    w.action_toggle_diagnostics = dock_action(w.diagnostics_panel, "Diagnostics panel", "Ctrl+Shift+X")
    w.action_toggle_citations = dock_action(w.citation_panel, "Citations panel", "Ctrl+Shift+Z")
    w.action_reload_plugins = mk("Reload plugins", w.plugins.reload_all)
    from .script_picker import show_script_picker
    w.action_script_picker = mk("Run saved script…", lambda: show_script_picker(w), "F7")
    w.action_video_play_pause = mk("Play / pause video", w.viewer.video_view.toggle_play_pause)
    w.action_video_stop = mk("Stop video", w.viewer.video_view.stop)
    w.action_image_next_frame = mk("Next frame", lambda: w.viewer.image_view.step_frame(+1))
    w.action_image_prev_frame = mk("Previous frame", lambda: w.viewer.image_view.step_frame(-1))

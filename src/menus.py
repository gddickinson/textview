"""Menu-bar assembly. Pulled out of `app.py` to keep that file under the
500-line cap. Each top-level menu is a list of `QAction` references already
attached to MainWindow as `window.action_*` (see `actions.build`).
"""
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtCore import QUrl

from . import agent_scripts


def _add(menu, *items):
    for a in items:
        menu.addSeparator() if a is None else menu.addAction(a)


def _rebuild_scripts_menu(menu, window):
    """Refresh the Scripts submenu from the agent_scripts directory.
    Wired to `aboutToShow` so each open re-reads the directory and
    picks up scripts the LLM created since last time."""
    menu.clear()
    scripts = agent_scripts.list_scripts()
    if not scripts:
        a = QAction("(no scripts saved yet)", menu)
        a.setEnabled(False)
        menu.addAction(a)
    else:
        for s in scripts:
            label = f"{s.name}.{s.language[:2]}"
            if s.description:
                label += f"  —  {s.description}"
            a = QAction(label, menu)
            a.setData(str(s.path))
            a.triggered.connect(
                lambda _checked=False, p=str(s.path):
                    window.run.panel.run_file(p))
            menu.addAction(a)
    menu.addSeparator()
    menu.addAction(window.action_script_picker)
    a = QAction("Open scripts folder…", menu)
    a.triggered.connect(lambda: (
        agent_scripts.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True),
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(agent_scripts.SCRIPTS_DIR))),
    ))
    menu.addAction(a)


def build(w):
    """Populate `w.menuBar()` from already-built actions."""
    mb = w.menuBar()

    m_file = mb.addMenu("&File")
    _add(m_file, w.action_new_window, w.action_new_tab, w.action_new_from_template,
         w.action_open, w.action_quick_open,
         w.action_open_url, w.action_open_folder, w.action_save,
         w.action_save_as, w.action_reload, w.action_close_file,
         w.action_close_all, w.action_detach_tab, None)
    w.recent.attach_menu(m_file.addMenu("Open recent"))
    m_export = m_file.addMenu("Export")
    _add(m_export, w.action_export_html, w.action_export_pdf,
         w.action_export_md, w.action_export_txt,
         w.action_export_rtf, w.action_export_png)
    _add(m_file, w.action_print, None, w.action_quit)

    _add(mb.addMenu("&Edit"), w.action_undo, w.action_redo, None,
         w.action_find, w.action_workspace_search, w.action_goto_line, w.action_toggle_comment,
         None, w.action_move_line_up, w.action_move_line_down,
         w.action_dup_line, w.action_select_line,
         None, w.action_to_spaces, w.action_to_tabs,
         w.action_le_lf, w.action_le_crlf,
         None, w.action_compare_file, w.action_compare_git,
         None, w.action_inline_suggest,
         None, w.action_insert_snippet, w.action_save_snippet,
         None, w.action_lsp_hover, w.action_lsp_goto_def, w.action_lsp_find_refs,
         None, w.action_edit_mode, w.action_copy_all)

    _add(mb.addMenu("&Run"), w.action_run, w.action_run_selection,
         w.action_stop_run, None, w.action_compile_latex,
         w.action_archive_extract_one, w.action_archive_extract_all, None,
         w.action_toggle_runner,
         w.action_python_repl, w.action_pick_python, w.action_jupyter_console,
         w.action_notebook_start, w.action_notebook_run_all,
         w.action_notebook_add_code, w.action_notebook_add_md, w.action_notebook_delete,
         w.action_notebook_to_code, w.action_notebook_to_md,
         w.action_notebook_move_up, w.action_notebook_move_down, None,
         w.action_watch_folder, None,
         w.action_reload_hooks, w.action_hooks_dir,
         w.action_reload_plugins)

    _add(mb.addMenu("&View"), w.action_zoom_in, w.action_zoom_out,
         w.action_zoom_reset, None, w.action_toggle_render,
         w.action_toggle_folding, w.action_fullscreen, None, w.action_toggle_config,
         w.action_toggle_metadata, w.action_toggle_chat,
         w.action_toggle_project, w.action_toggle_image_panel,
         w.action_toggle_terminal, w.action_toggle_diagnostics,
         w.action_toggle_citations, None,
         w.action_command_palette, w.action_cheat_sheet)

    _add(mb.addMenu("&Image"), w.action_image_rotate,
         w.action_image_prev, w.action_image_next, None,
         w.action_image_prev_frame, w.action_image_next_frame, None,
         w.action_slideshow, w.action_image_save_as)

    m_media = mb.addMenu("&Media")
    _add(m_media, w.action_video_play_pause, w.action_video_stop)

    m_pdf = mb.addMenu("&PDF")
    _add(m_pdf, w.action_pdf_rotate_cw, w.action_pdf_rotate_ccw,
         w.action_pdf_rotate_180, None,
         w.action_pdf_delete_page, w.action_pdf_extract,
         w.action_pdf_reorder, None,
         w.action_pdf_insert_after, w.action_pdf_insert_start, None,
         w.action_pdf_merge, None)
    m_annot = m_pdf.addMenu("Annotations")
    _add(m_annot, w.action_pdf_annot_sticky, w.action_pdf_annot_text,
         w.action_pdf_annot_hl, w.action_pdf_annot_rect,
         w.action_pdf_annot_circle, None,
         w.action_pdf_annot_list, w.action_pdf_annot_del_one,
         w.action_pdf_annot_clear)
    # Mouse-driven annotation mode (v3.5 phase 2b).
    m_modes = m_pdf.addMenu("Annotate mode (mouse)")
    _add(m_modes, w.action_pdf_mode_sticky, w.action_pdf_mode_freetext,
         w.action_pdf_mode_highlight, w.action_pdf_mode_underline,
         w.action_pdf_mode_strikeout, None,
         w.action_pdf_mode_rect, w.action_pdf_mode_circle, None,
         w.action_pdf_mode_off)

    m_table = mb.addMenu("&Table")
    # Ctrl+T (action_toggle_render) is the universal "toggle render" — for CSV
    # it flips between table view and code view. Re-listing it here makes the
    # operation discoverable from the Table menu without claiming a second
    # shortcut.
    _add(m_table, w.action_toggle_render, w.action_toggle_spreadsheet,
         w.action_switch_sheet, w.action_run_sql, w.action_table_copy_tsv)

    m_scripts = mb.addMenu("&Scripts")
    # Dynamic menu: rebuilt every time the user opens it so newly-saved
    # scripts appear without an app restart.
    m_scripts.aboutToShow.connect(
        lambda menu=m_scripts: _rebuild_scripts_menu(menu, w))
    # Pre-populate once so the menu has structure before first open.
    _rebuild_scripts_menu(m_scripts, w)

    w.bookmarks.attach_menu(mb.addMenu("&Bookmarks"))

    m_go = mb.addMenu("&Go")
    _add(m_go, w.action_home, w.action_open_url, None,
         w.action_view_source, w.action_devtools, w.action_reading_mode)

    m_help = mb.addMenu("&Help")
    _add(m_help, w.action_docs_index, None,
         w.action_docs_overview, w.action_docs_workspace,
         w.action_docs_unknown, w.action_docs_security,
         w.action_docs_formats, w.action_docs_shortcuts,
         w.action_docs_notebook, w.action_docs_lsp, w.action_docs_chat,
         w.action_docs_scripts, w.action_docs_plugins, w.action_docs_hooks, None,
         w.action_docs_agent_api, w.action_docs_control, w.action_docs_arch,
         w.action_docs_trouble, None,
         w.action_format_db,
         w.action_security_report, w.action_quarantine_browser, None,
         w.action_cheat_sheet)

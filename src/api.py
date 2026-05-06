"""Stable façade over `MainWindow` internals.

Hooks, plugins, and LLM tools all go through `AppAPI` instead of
poking `MainWindow` attributes directly. That way internal refactors
don't break user scripts. New methods can be added; renaming or
removing a method is a public-API breaking change.

`api.window()` returns the live `MainWindow` for power users — use
sparingly because it bypasses the contract.
"""
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QDockWidget


class AppAPI:
    """Single object that scripts / plugins / LLMs talk to."""

    def __init__(self, window):
        self._w = window

    # -- introspection ------------------------------------------------------

    def window(self):
        return self._w

    def version(self) -> str:
        return "1.0"

    # -- files --------------------------------------------------------------

    def open(self, path: str) -> None:
        self._w.open_file(str(path))

    def current_path(self) -> str | None:
        return self._w._current_path

    def current_format(self) -> str:
        return self._w._current_format

    def current_text(self) -> str:
        return self._w._current_content

    def set_text(self, text: str) -> None:
        """Replace the buffer (and `_current_content`). The user must be in
        edit mode for this to be persistable; otherwise the change is in
        memory only."""
        self._w.viewer.code.setPlainText(text)
        self._w._current_content = text

    def save(self) -> bool:
        return bool(self._w.edit.save())

    def save_as(self, path: str) -> None:
        Path(path).write_text(self._w._current_content)

    def reload(self) -> None:
        self._w.on_reload()

    def close_file(self) -> None:
        self._w._show_welcome()

    # -- tabs ---------------------------------------------------------------

    def tabs(self) -> list[str]:
        return self._w.tab_bar.paths()

    def active_tab(self) -> int:
        return self._w.tab_bar.bar.currentIndex()

    def switch_tab(self, idx: int) -> None:
        self._w.tab_bar.bar.setCurrentIndex(int(idx))

    def close_tab(self, idx: int) -> None:
        self._w.tab_bar._on_close(int(idx))

    def close_all_tabs(self) -> None:
        self._w.tab_bar.close_all()

    # -- editor / search ----------------------------------------------------

    def selection(self) -> str:
        # Qt uses U+2029 (PARAGRAPH SEPARATOR) and U+2028 (LINE
        # SEPARATOR) for newlines in `selectedText()`; normalise to
        # real `\n` so callers can splitlines / count newlines.
        s = self._w.viewer.code.textCursor().selectedText()
        return s.replace(" ", "\n").replace(" ", "\n")

    def replace_selection(self, text: str) -> None:
        c = self._w.viewer.code.textCursor()
        c.insertText(text)

    def insert_text(self, text: str) -> None:
        self._w.viewer.code.textCursor().insertText(text)

    def line_count(self) -> int:
        return self._w.viewer.code.document().blockCount()

    def goto_line(self, n: int) -> None:
        from PyQt6.QtGui import QTextCursor
        doc = self._w.viewer.code.document()
        block = doc.findBlockByNumber(max(0, int(n) - 1))
        if not block.isValid():
            return
        c = QTextCursor(block)
        self._w.viewer.code.setTextCursor(c)

    def find(self, text: str) -> bool:
        return self._w.viewer.code.find(text)

    def replace_all(self, find: str, replace: str) -> int:
        if not find:
            return 0
        body = self._w.viewer.code.toPlainText()
        n = body.count(find)
        if n:
            self.set_text(body.replace(find, replace))
        return n

    # -- settings -----------------------------------------------------------

    def get_setting(self, name: str):
        return getattr(self._w.settings_manager.display, name, None)

    def set_setting(self, name: str, value) -> None:
        self._w.settings_manager.update(name, value)

    def theme(self) -> str:
        return self._w.settings_manager.display.theme

    def set_theme(self, name: str) -> None:
        self._w.settings_manager.update("theme", name)

    def themes(self) -> list[str]:
        from .themes import theme_names
        return theme_names()

    # -- run / shell --------------------------------------------------------

    def run_shell(self, cmd: str, cwd: str | None = None) -> None:
        self._w.run.panel.run_shell(cmd, cwd=cwd)

    def run_python_snippet(self, code: str, cwd: str | None = None) -> None:
        self._w.run.panel.run_python_snippet(code, cwd=cwd)

    def run_current(self) -> None:
        self._w.run.run_current()

    def stop_run(self) -> None:
        self._w.run.stop()

    # -- tables -------------------------------------------------------------

    def table_model(self):
        return self._w.viewer.table_view.model()

    def table_header(self) -> list[str]:
        m = self.table_model()
        return m.header() if m else []

    def table_data(self, visible_only: bool = True) -> list[list[str]]:
        """Returns the table as list-of-rows. `visible_only=True` (default)
        respects the active filter. Pass False to get every underlying row."""
        m = self.table_model()
        if m is None:
            return []
        if visible_only:
            return [[m.get_value(r, c) for c in range(m.columnCount())]
                    for r in range(m.rowCount())]
        return [list(r) for r in m._rows]

    def table_set_filter(self, col, op: str, value: str) -> None:
        m = self.table_model()
        if m is None:
            return
        if isinstance(col, str):
            try:
                col = m.header().index(col)
            except ValueError:
                return
        m.set_filter(col, op, value)

    def table_clear_filter(self) -> None:
        m = self.table_model()
        if m: m.clear_filter()

    def table_sort(self, col, ascending: bool = True) -> None:
        m = self.table_model()
        if m is None:
            return
        if isinstance(col, str):
            try: col = m.header().index(col)
            except ValueError: return
        m.sort(col, Qt.SortOrder.AscendingOrder if ascending
                    else Qt.SortOrder.DescendingOrder)

    def table_insert_row(self, values: list[str] | None = None) -> None:
        m = self.table_model()
        if m: m.insert_row(values=values)

    def table_delete_rows(self, view_rows: list[int]) -> None:
        m = self.table_model()
        if m: m.delete_rows(view_rows)

    def table_plot(self, kind: str, x: str | None = None,
                   y: list[str] | None = None,
                   title: str = "", save: str | None = None):
        """Open the plot dialog or render to a PNG file when `save` is given.

        `kind`: Line / Bar / Scatter / Histogram / Pie / Box.
        `x`: column name or None.
        `y`: list of column names; defaults to all numeric columns.
        """
        m = self.table_model()
        if m is None:
            return
        from .plot_dialog import PlotDialog
        dlg = PlotDialog(m, self._w)
        dlg.combo_type.setCurrentText(kind)
        if x is not None:
            try: idx = m.header().index(x); dlg.combo_x.setCurrentIndex(idx + 1)
            except ValueError: pass
        if y:
            for col_idx, cb in dlg.y_checks:
                cb.setChecked(m.header()[col_idx] in y and cb.isEnabled())
        if title:
            dlg.le_title.setText(title)
        dlg._plot()
        if save:
            dlg.figure.savefig(save, dpi=150, bbox_inches="tight")
            dlg.deleteLater()
        else:
            dlg.exec()

    # -- status / notifications ---------------------------------------------

    def status(self, msg: str, ms: int = 3000) -> None:
        self._w.statusBar().showMessage(str(msg), int(ms))

    # -- UI extension (for plugins) -----------------------------------------

    def add_action(self, label: str, callback: Callable,
                   shortcut: str | None = None,
                   menu: str | None = "Plugins") -> QAction:
        """Create a QAction, attach to `MainWindow`, optionally add to a
        menu. Returns the action so callers can wire it elsewhere or
        remove it on plugin unload."""
        act = QAction(label, self._w)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(callback)
        self._w.addAction(act)
        if menu:
            self._ensure_menu(menu).addAction(act)
        return act

    def remove_action(self, action: QAction) -> None:
        # Walk all menus in the menu bar and remove the action from each.
        from PyQt6.QtWidgets import QMenu
        for child in self._w.menuBar().findChildren(QMenu):
            child.removeAction(action)
        self._w.removeAction(action)
        try:
            action.deleteLater()
        except Exception:
            pass

    def _ensure_menu(self, title: str):
        bar = self._w.menuBar()
        for a in bar.actions():
            if a.menu() and a.text().replace("&", "") == title:
                return a.menu()
        return bar.addMenu(title)

    def add_dock(self, widget, title: str = "Plugin",
                 area: str = "right") -> QDockWidget:
        """Wrap `widget` in a `QDockWidget` and attach it to MainWindow."""
        area_map = {
            "right": Qt.DockWidgetArea.RightDockWidgetArea,
            "left":  Qt.DockWidgetArea.LeftDockWidgetArea,
            "top":   Qt.DockWidgetArea.TopDockWidgetArea,
            "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
        }
        dock = QDockWidget(title, self._w)
        dock.setWidget(widget)
        self._w.addDockWidget(area_map.get(area, Qt.DockWidgetArea.RightDockWidgetArea),
                               dock)
        return dock

    def remove_dock(self, dock: QDockWidget) -> None:
        try:
            self._w.removeDockWidget(dock)
            dock.deleteLater()
        except Exception:
            pass

    # -- agent scripts -----------------------------------------------------

    def scripts_list(self) -> list:
        from . import agent_scripts
        return agent_scripts.list_scripts()

    def scripts_read(self, name: str):
        from . import agent_scripts
        return agent_scripts.read_script(name)

    def scripts_create(self, name: str, language: str, body: str):
        from . import agent_scripts
        return agent_scripts.write_script(name, language, body,
                                          allow_overwrite=False)

    def scripts_update(self, name: str, body: str):
        from . import agent_scripts
        return agent_scripts.update_script(name, body)

    def scripts_delete(self, name: str) -> bool:
        from . import agent_scripts
        return agent_scripts.delete_script(name)

    def scripts_run(self, name: str) -> bool:
        from . import agent_scripts
        s = agent_scripts.read_script(name)
        if s is None:
            return False
        try:
            self._w.run.panel.run_file(str(s.path))
            return True
        except Exception:
            return False

    # -- hooks (programmatic event subscription) ---------------------------

    def on(self, event: str, callback: Callable) -> Callable:
        """Subscribe a callback to an event. Returns an unsubscribe fn.
        Events: file_opened, file_saved, run_finished, chat_response."""
        registry = self._w.hooks
        registry.subscribe(event, callback)
        return lambda: registry.unsubscribe(event, callback)

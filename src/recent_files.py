"""Recent-files menu, persisted in QSettings.

`RecentFilesController` rebuilds its menu on every change. `add(path)` is
called from `MainWindow.open_file` after a successful load. Most-recent
entry first; capped at `MAX`.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtGui import QAction


MAX = 12


class RecentFilesController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.menu = None

    def attach_menu(self, menu):
        self.menu = menu
        self.rebuild()

    @staticmethod
    def _load() -> list[str]:
        return [p for p in (QSettings().value("recent/paths", []) or []) if p]

    @staticmethod
    def _save(items):
        QSettings().setValue("recent/paths", list(items))

    def add(self, path: str):
        if not path:
            return
        resolved = str(Path(path).resolve())
        items = self._load()
        items = [p for p in items if p != resolved]
        items.insert(0, resolved)
        del items[MAX:]
        self._save(items)
        self.rebuild()

    def clear(self):
        self._save([])
        self.rebuild()

    def rebuild(self):
        if self.menu is None:
            return
        self.menu.clear()
        items = self._load()
        if not items:
            a = QAction("(no recent files)", self.menu)
            a.setEnabled(False)
            self.menu.addAction(a)
            return
        for i, path in enumerate(items, start=1):
            label = f"&{i if i < 10 else ''}  {Path(path).name}  —  {Path(path).parent}"
            a = QAction(label, self.menu)
            a.setToolTip(path)
            a.triggered.connect(lambda _checked=False, p=path: self.window.open_file(p))
            self.menu.addAction(a)
        self.menu.addSeparator()
        clr = QAction("Clear recent files", self.menu)
        clr.triggered.connect(self.clear)
        self.menu.addAction(clr)

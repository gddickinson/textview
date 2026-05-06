"""Project tree dock — `QFileSystemModel` + `QTreeView`.

`File → Open folder…` mounts a directory; double-click on a file opens
it in a new tab via `MainWindow.open_file`. The folder root persists in
`QSettings` so reopening the app restores the last project. Hidden /
dotfiles are kept off by default.
"""
from PyQt6.QtCore import Qt, QDir, QSettings
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import QDockWidget, QTreeView, QFileDialog


class ProjectPanel(QDockWidget):
    def __init__(self, window):
        super().__init__("Project", window)
        self.window = window
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._model = QFileSystemModel(self)
        self._model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files
            | QDir.Filter.NoDotAndDotDot
        )
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(True)
        # Hide everything except the file/folder name column.
        for col in range(1, 4):
            self._tree.setColumnHidden(col, True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(14)
        self._tree.activated.connect(self._on_activated)
        self.setWidget(self._tree)
        self.setMinimumWidth(240)
        # Restore last folder, if any.
        last = QSettings().value("project/folder")
        if last:
            try:
                self.set_root(str(last))
            except Exception:
                pass

    def set_root(self, path: str):
        idx = self._model.setRootPath(path)
        self._tree.setRootIndex(idx)
        QSettings().setValue("project/folder", path)
        self.window.statusBar().showMessage(f"Project: {path}", 4000)

    def open_dialog(self):
        start = QSettings().value("project/folder") or ""
        folder = QFileDialog.getExistingDirectory(self.window, "Open folder", start)
        if folder:
            self.set_root(folder)
            self.show(); self.raise_()

    def _on_activated(self, index):
        path = self._model.filePath(index)
        if self._model.isDir(index):
            return
        self.window.open_file(path)

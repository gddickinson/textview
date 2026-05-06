"""Watch the open file for external changes and reload.

Most editors do an atomic-replace save (write a temp file, rename over the
original), which makes the inode disappear briefly. We re-add the path on
each fileChanged so subsequent saves still notify us. A short debounce
timer batches the storms of notifications a save typically produces.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, QFileSystemWatcher, QTimer
from PyQt6.QtWidgets import QMessageBox


class DiskWatcher(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_changed)

    def watch(self, path: str):
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        if path:
            self._watcher.addPath(path)

    def _on_changed(self, path: str):
        if path != self.window._current_path:
            return
        QTimer.singleShot(150, lambda: self._reload(path))

    def _reload(self, path: str):
        if not Path(path).exists():
            return
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        d = self.window.settings_manager.display
        if self.window.edit.modified or not d.auto_reload_on_disk_change:
            ret = QMessageBox.question(
                self.window, "File changed on disk",
                f"{Path(path).name}\n\nThe file changed on disk. Reload?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        # Disk-watcher already ran its own prompt above when relevant; skip
        # `confirm_discard` so the user isn't asked twice.
        self.window.open_file(path, confirm=False)

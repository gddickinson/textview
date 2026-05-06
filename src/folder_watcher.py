"""Watch a folder; run a configurable shell command when files change.

Useful for "rebuild on save" / live test loops without leaving TextView:
point at a directory, set the command, and any file change triggers
`run_command` in the bottom Terminal panel. Multiple changes in quick
succession debounce to a single run.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, QFileSystemWatcher, QTimer, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QHBoxLayout, QFileDialog, QLabel, QCheckBox,
)


class FolderWatcher(QObject):
    triggered = pyqtSignal(str)   # last-changed path

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.watcher = QFileSystemWatcher(self)
        self.command = ""
        self.cwd: str | None = None
        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._fire)
        self.watcher.directoryChanged.connect(self._on_change)
        self.watcher.fileChanged.connect(self._on_change)
        self._restore()

    def watch_paths(self) -> list[str]:
        return self.watcher.directories() + self.watcher.files()

    def stop(self):
        if self.watch_paths():
            self.watcher.removePaths(self.watch_paths())
        self.command = ""
        self._save()
        self.window.statusBar().showMessage("Folder watch stopped.", 3000)

    def configure(self, folder: str, command: str, cwd: str | None,
                  recursive: bool = True):
        if self.watch_paths():
            self.watcher.removePaths(self.watch_paths())
        if folder:
            self.watcher.addPath(folder)
            if recursive:
                for p in Path(folder).rglob("*"):
                    if p.is_dir():
                        self.watcher.addPath(str(p))
        self.command = command or ""
        self.cwd = cwd
        self._save()
        self.window.statusBar().showMessage(
            f"Watching {folder} → `{command}`", 4000,
        )

    # -- handlers ----------------------------------------------------------

    def _on_change(self, path: str):
        # 200ms debounce — most editors fire several events per save.
        self._last_path = path
        self._debounce.start(200)

    def _fire(self):
        if not self.command:
            return
        self.triggered.emit(getattr(self, "_last_path", ""))
        self.window.run.panel.run_shell(self.command, cwd=self.cwd)

    # -- persistence -------------------------------------------------------

    def _save(self):
        s = QSettings()
        s.setValue("watch/folder", self.watcher.directories()[0]
                   if self.watcher.directories() else "")
        s.setValue("watch/command", self.command)
        s.setValue("watch/cwd", self.cwd or "")

    def _restore(self):
        s = QSettings()
        folder = s.value("watch/folder") or ""
        command = s.value("watch/command") or ""
        cwd = s.value("watch/cwd") or ""
        if folder and command:
            self.configure(str(folder), str(command), str(cwd) or None)


def show_watch_dialog(window):
    """Modal config dialog: pick folder + command + recursive."""
    s = QSettings()
    dlg = QDialog(window)
    dlg.setWindowTitle("Watch folder")
    dlg.setModal(True); dlg.resize(540, 200)
    v = QVBoxLayout(dlg); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)
    f = QFormLayout()

    folder_row = QHBoxLayout()
    folder = QLineEdit(s.value("watch/folder") or "")
    pick = QPushButton("Browse…")
    def _pick():
        d = QFileDialog.getExistingDirectory(dlg, "Watch folder", folder.text() or "")
        if d: folder.setText(d)
    pick.clicked.connect(_pick)
    folder_row.addWidget(folder, 1); folder_row.addWidget(pick)
    f.addRow("Folder:", folder_row)

    cmd = QLineEdit(s.value("watch/command") or "")
    cmd.setPlaceholderText("e.g. pytest -q  or  python build.py")
    f.addRow("Command:", cmd)

    cwd = QLineEdit(s.value("watch/cwd") or "")
    cwd.setPlaceholderText("(defaults to the watched folder)")
    f.addRow("Working dir:", cwd)

    cb_rec = QCheckBox("Recursive (watch sub-folders)")
    cb_rec.setChecked(True)
    f.addRow(cb_rec)

    hint = QLabel("<i>Changes are debounced (200 ms). Saving any file in the "
                  "watched folder runs the command in the Terminal panel.</i>")
    hint.setWordWrap(True); f.addRow(hint)
    v.addLayout(f)

    btns = QHBoxLayout(); btns.addStretch()
    b_stop = QPushButton("Stop watching")
    b_stop.clicked.connect(lambda: (window.folder_watch.stop(), dlg.accept()))
    btns.addWidget(b_stop)
    b_start = QPushButton("Start"); b_start.setDefault(True)
    def _start():
        if not folder.text() or not cmd.text():
            return
        window.folder_watch.configure(
            folder.text(), cmd.text(), cwd.text() or None, cb_rec.isChecked(),
        )
        dlg.accept()
    b_start.clicked.connect(_start)
    btns.addWidget(b_start)
    v.addLayout(btns)
    dlg.exec()

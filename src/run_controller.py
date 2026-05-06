"""Glue between MainWindow and `RunnerPanel`.

Owns the panel + the action handlers. Mirrors the shape of `WebController`
and `RichDocController` so app.py stays slim.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QSettings
from PyQt6.QtWidgets import QMessageBox

from .runner_panel import RunnerPanel


def _trusted_paths() -> set:
    return set(QSettings().value("runner/trusted_paths", []) or [])


def _trust_path(path: str):
    s = QSettings()
    paths = set(s.value("runner/trusted_paths", []) or [])
    paths.add(str(Path(path).resolve()))
    s.setValue("runner/trusted_paths", list(paths))


class RunController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.panel = RunnerPanel(window); self.panel.setObjectName("runner_panel")
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.panel)
        self.panel.hide()
        self.apply_settings(window.settings_manager.display)

    def apply_settings(self, d):
        self.panel.runner.set_resource_limits(
            getattr(d, "runner_cpu_seconds", 60),
            getattr(d, "runner_max_memory_mb", 1024),
        )
        self.panel.runner.set_python_interpreter(getattr(d, "python_interpreter", "python3"))
        # Sandbox wrap (off by default — runner already has rlimits).
        self.panel.runner._sandbox_no_network = bool(
            getattr(d, "security_sandbox_runner", False))

    def toggle_action(self):
        a = self.panel.toggleViewAction()
        a.setText("Terminal panel")
        a.setShortcut("F12")
        return a

    def run_current(self):
        w = self.window
        if not w._current_path:
            w.statusBar().showMessage("No file to run.", 3000)
            return
        # Markup "runs" by opening in the embedded browser.
        if w._current_format in {"html", "markdown"}:
            d = w.settings_manager.display
            allow = w.web.security.consult_local_remote(w._current_path, d)
            if allow and not d.web_local_remote_access:
                # Per-file grant — temporarily flip the profile's flag.
                w.web.security.apply_profile_settings(d, force_remote=True)
            w.open_url("file://" + str(Path(w._current_path).resolve()))
            return
        if w._current_format in {"image", "pdf", "docx", "rtf", "epub", "odt"}:
            w.statusBar().showMessage(
                f"Can't run a {w._current_format} file.", 3000
            )
            return
        # Notebooks have an in-app runner; don't shell out to `jupyter execute`.
        if w._current_format == "notebook":
            w.viewer.notebook_view.run_all(); return
        if w.edit.modified and w.settings_manager.display.runner_save_before_run:
            if not w.edit.save():
                return
        if not self._confirm_run(w._current_path):
            return
        ext = w._current_path.rsplit(".", 1)[-1].lower() if "." in w._current_path else ""
        if ext not in self.panel.runner.supported_extensions():
            ret = QMessageBox.question(
                w, "Run as shell?",
                f"No interpreter is configured for .{ext} files. "
                f"Run the file as a shell script (`bash {ext_basename(w._current_path)}`)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            self.panel.run_shell(f"bash {w._current_path}")
            return
        self.panel.run_file(w._current_path)

    def _confirm_run(self, path: str) -> bool:
        """Prompt the user before running a file we haven't run before.

        Returns True if it's OK to proceed. Honors a "trusted paths" set in
        QSettings so the user isn't pestered for files they've already
        approved. Setting `runner_confirm_first_run` can disable the prompt
        globally.
        """
        d = self.window.settings_manager.display
        if not d.runner_confirm_first_run:
            return True
        resolved = str(Path(path).resolve())
        if resolved in _trusted_paths():
            return True
        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Run file?")
        msg.setText(f"Run\n  {resolved}\nas executable code?")
        msg.setInformativeText(
            "This will execute the file with full access to your account "
            "(network, files, processes). Only run files you trust."
        )
        b_once = msg.addButton("Run once", QMessageBox.ButtonRole.AcceptRole)
        b_always = msg.addButton("Always for this file", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is b_always:
            _trust_path(resolved)
            return True
        if clicked is b_once:
            return True
        return False

    def run_selection(self):
        w = self.window
        cursor = w.viewer.code.textCursor()
        if not cursor.hasSelection():
            return self.run_current()
        # Qt uses U+2029 as the line separator inside selections
        code = cursor.selectedText().replace("\u2029", "\n")
        cwd = (
            __import__("pathlib").Path(w._current_path).parent.as_posix()
            if w._current_path else None
        )
        self.panel.run_python_snippet(code, cwd=cwd)

    def stop(self):
        self.panel.stop()


def ext_basename(path):
    from pathlib import Path
    return Path(path).name

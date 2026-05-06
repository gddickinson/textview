"""Edit-mode controller: read-only toggle, save / save as, dirty tracking,
and an unsaved-changes prompt.

Held by the MainWindow. Connects `document().modificationChanged` to a
signal the window listens to for live title updates.
"""
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from .file_loader import DOCUMENT_FORMATS


class EditController(QObject):
    state_changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.editing = False
        self.modified = False

    @staticmethod
    def can_edit(fmt: str) -> bool:
        # Documents are extracted, not editable in place.
        return fmt not in DOCUMENT_FORMATS

    def attach(self, viewer):
        viewer.code.document().modificationChanged.connect(self._on_modified_changed)

    def reset(self):
        """Called whenever a new file is loaded."""
        self.editing = False
        code = self.window.viewer.code
        code.setReadOnly(True)
        code.document().setModified(False)
        self.modified = False
        self.state_changed.emit()

    def toggle_editing(self):
        self.set_editing(not self.editing)

    def set_editing(self, on: bool):
        if on and not self.can_edit(self.window._current_format):
            QMessageBox.information(
                self.window, "Editing unavailable",
                "This format is read-only because we can't safely write back to it.",
            )
            return
        if on:
            # Switch to source view — editing rendered HTML/PDF doesn't apply.
            # Use the main window's content-load helper so the undo stack
            # gets cleared after syntax-highlighting/line-height formatting,
            # leaving Ctrl+Z to operate purely on user edits.
            v = self.window.viewer
            if v.mode() != v.MODE_CODE:
                self.window._populate_code_view()
                v.show_code()
        self.editing = on
        self.window.viewer.code.setReadOnly(not on)
        if on:
            self.window.viewer.code.setFocus()
        self.state_changed.emit()

    def _prepare_save_text(self) -> str:
        """Apply format-on-save → trim-trailing-whitespace → ensure-final-NL,
        in that order, before writing to disk. Each step is settable so
        they can be turned off for files where they'd be destructive.
        """
        text = self.window.viewer.code.toPlainText()
        d = self.window.settings_manager.display
        if d.format_on_save and self.window._current_format:
            from .formatters import format_text
            text, msg = format_text(text, self.window._current_format)
            if msg:
                self.window.statusBar().showMessage(msg, 4000)
        if d.trim_trailing_whitespace_on_save:
            text = "\n".join(line.rstrip() for line in text.split("\n"))
        if d.ensure_final_newline_on_save and text and not text.endswith("\n"):
            text += "\n"
        return text

    def save(self) -> bool:
        if self.window._current_path is None:
            return self.save_as()
        # Notebooks save via nbformat (cells + outputs), not as text.
        if self.window._current_format == "notebook":
            ok = self.window.viewer.notebook_view.save()
            if ok: self.window.statusBar().showMessage(
                f"Saved → {self.window._current_path}", 3000)
            return ok
        try:
            content = self._prepare_save_text()
            Path(self.window._current_path).write_text(content, encoding="utf-8")
            # Reflect the cleaned content back into the buffer so the user
            # sees what we actually wrote.
            self.window.viewer.code.setPlainText(content)
            self.window._current_content = content
            self.window.viewer.code.document().setModified(False)
            self.window.statusBar().showMessage(
                f"Saved → {self.window._current_path}", 3000
            )
            if hasattr(self.window, "hooks"):
                self.window.hooks.fire("on_file_saved", self.window._current_path)
            return True
        except OSError as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return False

    def save_as(self) -> bool:
        suggested = self.window._current_path or "untitled.txt"
        path, _ = QFileDialog.getSaveFileName(self.window, "Save as", suggested)
        if not path:
            return False
        try:
            content = self._prepare_save_text()
            Path(path).write_text(content, encoding="utf-8")
            self.window.viewer.code.setPlainText(content)
            self.window._current_path = path
            self.window._current_content = content
            self.window.viewer.code.document().setModified(False)
            self.window.statusBar().showMessage(f"Saved → {path}", 3000)
            self.window.setWindowTitle(f"TextView — {Path(path).name}")
            return True
        except OSError as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return False

    def confirm_discard(self) -> bool:
        """Return True if it's OK to discard the current buffer's changes."""
        if not self.modified:
            return True
        ret = QMessageBox.question(
            self.window, "Unsaved changes",
            "There are unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Cancel:
            return False
        if ret == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def _on_modified_changed(self, modified):
        self.modified = modified
        self.state_changed.emit()

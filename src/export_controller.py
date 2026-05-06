"""Export-action handlers.

Holds the small set of "Export as X" methods that used to live on
MainWindow. Each one syncs unsaved edits, asks for a path, and writes.
For HTML we route through the active format's renderer so the output
matches what the viewer shows.
"""
import shutil

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QFileDialog, QApplication

from . import exporter
from .renderers import render_markdown_html
from .themes import get_theme
from pathlib import Path


class ExportController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.w = window

    def _suggest_name(self, ext):
        if self.w._current_path:
            return f"{Path(self.w._current_path).stem}.{ext}"
        return f"untitled.{ext}"

    def _dialog(self, ext, file_filter):
        if not self.w._current_content:
            return None
        path, _ = QFileDialog.getSaveFileName(
            self.w, "Export", self._suggest_name(ext), file_filter
        )
        return path

    def html(self):
        self.w._sync_content()
        path = self._dialog("html", "HTML (*.html)")
        if not path:
            return
        d = self.w.settings_manager.display
        theme = get_theme(d.theme)
        if self.w._current_format == "markdown":
            exporter.export_html_rendered(
                render_markdown_html(self.w._current_content, theme, d), path
            )
        elif self.w._current_format == "html":
            exporter.export_html_rendered(self.w._current_content, path)
        else:
            exporter.export_html_plain(self.w._current_content, path, theme)
        self.w.statusBar().showMessage(f"Exported HTML → {path}", 4000)

    def pdf(self):
        path = self._dialog("pdf", "PDF (*.pdf)")
        if not path:
            return
        if self.w.viewer.mode() == self.w.viewer.MODE_PDF and self.w._pdf.path:
            shutil.copyfile(self.w._pdf.path, path)
        else:
            exporter.export_pdf(self.w.viewer.active_widget(), path)
        self.w.statusBar().showMessage(f"Exported PDF → {path}", 4000)

    def _text_with(self, ext, file_filter, fn):
        self.w._sync_content()
        path = self._dialog(ext, file_filter)
        if path:
            fn(self.w._current_content, path)
            self.w.statusBar().showMessage(f"Saved → {path}", 4000)

    def md(self):
        self._text_with("md", "Markdown (*.md)", exporter.export_markdown)

    def txt(self):
        self._text_with("txt", "Plain text (*.txt)", exporter.export_plain)

    def rtf(self):
        self._text_with("rtf", "RTF (*.rtf)", exporter.export_rtf)

    def png(self):
        path = self._dialog("png", "PNG image (*.png)")
        if path:
            exporter.export_image(self.w.viewer.active_widget(), path)
            self.w.statusBar().showMessage(f"Saved snapshot → {path}", 4000)

    def print_(self):
        exporter.print_document(self.w.viewer.active_widget(), self.w)

    def copy_all(self):
        self.w._sync_content()
        QApplication.clipboard().setText(self.w._current_content)
        self.w.statusBar().showMessage("Copied all content to clipboard", 2000)

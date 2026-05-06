"""Image-mode action glue.

Owns the small handlers MainWindow used to call inline (rotate, browse
neighbors, fit, slideshow, save-as). Keeps app.py under its line budget.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class ImageController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.timeout.connect(lambda: self.step_in_folder(1))

    def _is_active(self) -> bool:
        return self.window.viewer.mode() == self.window.viewer.MODE_IMAGE

    def rotate(self, degrees: int = 90):
        if self._is_active():
            self.window.viewer.image_view.rotate(degrees)

    def step_in_folder(self, direction: int):
        if not self._is_active():
            return
        nxt = self.window.viewer.image_view.folder_neighbor(direction)
        if nxt:
            self.window.open_file(nxt)

    def fit(self):
        if self._is_active():
            self.window.viewer.image_view.fit_to_window()

    def actual_size(self):
        if self._is_active():
            self.window.viewer.image_view.actual_size()

    # -- slideshow ----------------------------------------------------------

    def toggle_slideshow(self, interval_ms: int = 3000):
        if not self._is_active():
            self.window.statusBar().showMessage(
                "Slideshow only available for image files.", 3000)
            return
        if self._slideshow_timer.isActive():
            self._slideshow_timer.stop()
            self.window.statusBar().showMessage("Slideshow stopped.", 2000)
        else:
            self._slideshow_timer.start(int(interval_ms))
            self.window.statusBar().showMessage(
                f"Slideshow on ({interval_ms} ms — Esc / re-toggle to stop).",
                4000,
            )

    def stop_slideshow(self):
        self._slideshow_timer.stop()

    # -- save-as / convert format -------------------------------------------

    def save_as(self):
        if not self._is_active() or not self.window._current_path:
            return
        suggested = Path(self.window._current_path).with_suffix(".png").name
        out, fil = QFileDialog.getSaveFileName(
            self.window, "Save image as", suggested,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;TIFF (*.tif *.tiff);;BMP (*.bmp);;ICO (*.ico)",
        )
        if not out:
            return
        try:
            from PIL import Image
            img = Image.open(self.window._current_path)
            # JPEG can't carry alpha — flatten to RGB.
            if out.lower().endswith((".jpg", ".jpeg")) and img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(out)
            self.window.statusBar().showMessage(f"Saved → {out}", 4000)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))

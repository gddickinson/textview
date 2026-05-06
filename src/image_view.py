"""Standalone image viewer widget.

`ImageView` displays one image file with zoom/pan, rotation, multi-page
TIFF navigation, animated-GIF playback, and live brightness / contrast /
saturation / gamma adjustment.

Two backends, switched per file:
  - **QMovie** for animated GIFs — Qt-native frame stepping, no per-frame
    adjustment (would defeat the animation).
  - **PIL → QImage** for everything else — supports multi-frame containers
    (TIFF, multi-frame WebP) via `Image.seek(idx)` and feeds the loaded
    frame through `image_adjust.adjust()` before display.

Zoom / fit-to-window / rotation are applied on top of whatever the
adjustment pipeline produces.
"""
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QRect, QSize
from PyQt6.QtGui import (
    QImageReader, QPixmap, QMovie, QPalette, QColor, QTransform, QPainter,
    QImage, QBrush,
)
from PyQt6.QtWidgets import QScrollArea, QLabel, QSizePolicy, QRubberBand

from . import image_adjust


def _checker_brush(size: int = 12) -> "QBrush":
    """Build a 2-tone checkered tile brush for the alpha-transparency backdrop."""
    img = QImage(size * 2, size * 2, QImage.Format.Format_RGB32)
    img.fill(QColor("#dddddd"))
    p = QPainter(img)
    p.fillRect(0, 0, size, size, QColor("#bbbbbb"))
    p.fillRect(size, size, size, size, QColor("#bbbbbb"))
    p.end()
    return QBrush(img)


# Default (identity) adjustment values.
_DEFAULTS = {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "gamma": 1.0}


class ImageView(QScrollArea):
    """Single-image viewer with zoom + pan, fit-to-window, multi-frame, and
    live B/C/S/G adjustments. Emits `loaded` after a successful load with
    `(frame_count, has_adjustments_support)` so a panel can sync its UI.
    """

    loaded = pyqtSignal(int, bool)
    frame_changed = pyqtSignal(int)
    pixmap_updated = pyqtSignal()   # fires after each adjustment / frame redraw
    color_picked = pyqtSignal(int, int, int, int, int)  # r, g, b, x, y (label coords)
    crop_selected = pyqtSignal(QRect)  # rubberband rect in label coords
    autoscale_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Initialize all state attributes first — QScrollArea.setWidget()
        # installs an event filter and immediately delivers events, so our
        # eventFilter override must find every attribute it touches.
        self._pil: Image.Image | None = None     # current frame (post-seek), pre-adjustment
        self._n_frames = 1
        self._frame_idx = 0
        self._pixmap: QPixmap | None = None      # post-adjustment, post-rotation, pre-zoom
        self._movie: QMovie | None = None
        self._zoom = 1.0
        self._fit = True
        self._rotation = 0
        self._adj = dict(_DEFAULTS)
        self._autoscale = False
        self._checkered = False
        self._current_path: str | None = None
        self._pick_mode = False
        self._crop_mode = False
        self._rubber_origin = None
        self._last_crop_rect: QRect | None = None

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._label.setMouseTracking(True)
        self._rubberband = QRubberBand(QRubberBand.Shape.Rectangle, self._label)
        self.setWidget(self._label)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(self.Shape.NoFrame)
        self._label.installEventFilter(self)

    # -- public API ----------------------------------------------------------

    def load(self, path: str) -> bool:
        self._clear()
        self._current_path = str(path)
        self._rotation = 0
        self._adj = dict(_DEFAULTS)
        self._autoscale = False
        self._frame_idx = 0
        self._n_frames = 1
        ext = Path(path).suffix.lower()

        if ext == ".gif":
            return self._load_gif(path)

        # PIL path — covers multi-frame TIFF/WebP, plus standard formats.
        if self._load_with_pil(path):
            self.loaded.emit(self._n_frames, True)
            return True
        # Fallback: QImageReader (covers SVG, HEIC plugins, weird formats).
        if self._load_with_qreader(path):
            self.loaded.emit(1, False)
            return True
        return False

    def _load_with_pil(self, path: str) -> bool:
        try:
            img = Image.open(path)
            img.load()
            n = getattr(img, "n_frames", 1) or 1
            self._pil = img
            # Wide-dynamic-range images (16-bit microscope TIFFs, float
            # rasters, etc.) benefit from auto-contrast on every frame —
            # without it the visible range often falls in 1-4 of 0-255
            # and the image looks black. Default the toggle on for those;
            # leave it off for ordinary 8-bit photos so they stay faithful.
            self._autoscale = img.mode in {"I", "I;16", "I;16B", "I;16L",
                                           "I;16N", "F"}
            self._n_frames = int(n)
            self._frame_idx = 0
            self._zoom = 1.0
            self._fit = True
            self._derive_pixmap()
            return True
        except Exception:
            return False

    def _load_with_qreader(self, path: str) -> bool:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return False
        self._pixmap = QPixmap.fromImage(img)
        self._zoom = 1.0
        self._fit = True
        self._render()
        return True

    def _load_gif(self, path: str) -> bool:
        self._movie = QMovie(str(path))
        if not self._movie.isValid():
            self._movie = None
            return False
        self._label.setMovie(self._movie)
        self._movie.jumpToFrame(0)
        self._movie.start()
        self._label.adjustSize()
        self.loaded.emit(1, False)
        return True

    def current_path(self) -> str | None:
        return self._current_path

    # -- multi-frame ---------------------------------------------------------

    def frame_count(self) -> int:
        return self._n_frames

    def current_frame(self) -> int:
        return self._frame_idx

    def set_frame(self, idx: int):
        if self._pil is None or self._n_frames <= 1:
            return
        idx = max(0, min(self._n_frames - 1, int(idx)))
        if idx == self._frame_idx:
            return
        try:
            self._pil.seek(idx)
        except (EOFError, OSError):
            return
        self._frame_idx = idx
        self._derive_pixmap()
        if self._fit:
            self.fit_to_window()
        self.frame_changed.emit(idx)

    def step_frame(self, direction: int):
        self.set_frame(self._frame_idx + int(direction))

    # -- adjustments ---------------------------------------------------------

    def set_adjustment(self, name: str, value: float):
        if name not in self._adj:
            return
        self._adj[name] = float(value)
        self._derive_pixmap()
        if self._fit:
            self.fit_to_window()

    def reset_adjustments(self):
        self._adj = dict(_DEFAULTS)
        self._derive_pixmap()
        if self._fit:
            self.fit_to_window()

    def set_autoscale(self, on: bool):
        self._autoscale = bool(on)
        self._derive_pixmap()
        if self._fit: self.fit_to_window()
        self.autoscale_changed.emit(self._autoscale)

    def is_autoscale(self) -> bool:
        return self._autoscale

    def adjustment(self, name: str) -> float:
        return self._adj.get(name, 1.0)

    def has_pil_source(self) -> bool:
        return self._pil is not None

    # -- rotate --------------------------------------------------------------

    def rotate(self, degrees: int = 90):
        if self._pixmap is None and self._pil is None:
            return
        self._rotation = (self._rotation + int(degrees)) % 360
        self._derive_pixmap()
        if self._fit:
            self.fit_to_window()

    # -- transparency backdrop ----------------------------------------------

    def set_checkered(self, on: bool):
        self._checkered = on
        if on:
            self.viewport().setAutoFillBackground(True)
            pal = self.viewport().palette()
            pal.setBrush(QPalette.ColorRole.Window, _checker_brush())
            self.viewport().setPalette(pal)

    def folder_neighbor(self, direction: int) -> str | None:
        if not self._current_path:
            return None
        p = Path(self._current_path)
        if not p.parent.exists():
            return None
        from .file_loader import IMAGE_FORMATS, detect_format
        siblings = sorted(
            f for f in p.parent.iterdir()
            if f.is_file() and detect_format(f) in IMAGE_FORMATS
        )
        if not siblings:
            return None
        try:
            i = siblings.index(p)
        except ValueError:
            i = 0
        return str(siblings[(i + direction) % len(siblings)])

    def info(self) -> str:
        if self._pixmap is not None:
            base = f"{self._pixmap.width()}×{self._pixmap.height()} px ({int(self._zoom * 100)}%)"
            if self._n_frames > 1:
                base += f" · frame {self._frame_idx + 1}/{self._n_frames}"
            return base
        if self._movie is not None:
            sz = self._movie.frameRect().size()
            return f"{sz.width()}×{sz.height()} px (animated)"
        return ""

    def set_background(self, color_str: str):
        pal = self.viewport().palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(color_str))
        self.viewport().setAutoFillBackground(True)
        self.viewport().setPalette(pal)

    # -- zoom / fit ----------------------------------------------------------

    def fit_to_window(self):
        if self._pixmap is None:
            return
        avail = self.viewport().size()
        scaled = self._pixmap.scaled(
            avail, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())
        self._zoom = scaled.width() / max(1, self._pixmap.width())
        self._fit = True

    def actual_size(self):
        if self._pixmap is None:
            return
        self._zoom = 1.0
        self._fit = False
        self._render()

    def zoom_by(self, factor: float):
        if self._pixmap is None:
            return
        self._zoom = max(0.05, min(20.0, self._zoom * factor))
        self._fit = False
        self._render()

    def zoom_in(self):
        self.zoom_by(1.25)

    def zoom_out(self):
        self.zoom_by(0.8)

    # -- internals -----------------------------------------------------------

    def _derive_pixmap(self):
        """Re-render `_pixmap` from `_pil` applying adjustments + rotation.

        For the QImageReader fallback path (`_pil is None`), `_pixmap` was
        already set at load time; rotation is applied here too.
        """
        if self._pil is not None:
            adjusted = image_adjust.adjust(
                self._pil, autoscale=self._autoscale, **self._adj)
            self._adjusted_pil = adjusted   # cached for histogram, etc.
            qimg = image_adjust.pil_to_qimage(adjusted)
            pm = QPixmap.fromImage(qimg)
            if self._rotation:
                t = QTransform().rotate(self._rotation)
                pm = pm.transformed(t, Qt.TransformationMode.SmoothTransformation)
            self._pixmap = pm
        elif self._pixmap is not None and self._rotation:
            t = QTransform().rotate(self._rotation)
            self._pixmap = self._pixmap.transformed(
                t, Qt.TransformationMode.SmoothTransformation)
            self._rotation = 0   # baked in for non-PIL path
        if not self._fit:
            self._render()
        self.pixmap_updated.emit()

    def current_adjusted_pil(self):
        """Return the post-adjustment PIL image used in the latest
        render, or the source `_pil` when adjustments are identity, or
        None for the QImageReader fallback path."""
        return getattr(self, "_adjusted_pil", None) or self._pil

    def _render(self):
        if self._pixmap is None:
            return
        new_w = max(1, int(self._pixmap.width() * self._zoom))
        new_h = max(1, int(self._pixmap.height() * self._zoom))
        scaled = self._pixmap.scaled(
            new_w, new_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def _clear(self):
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self._pil is not None:
            try:
                self._pil.close()
            except Exception:
                pass
            self._pil = None
        self._pixmap = None
        self._n_frames = 1
        self._frame_idx = 0
        self._label.clear()

    # -- pick / crop ---------------------------------------------------------

    def set_pick_mode(self, on: bool):
        self._pick_mode = bool(on)
        if on: self._crop_mode = False; self._rubberband.hide()
        self._update_cursor()

    def set_crop_mode(self, on: bool):
        self._crop_mode = bool(on)
        if on: self._pick_mode = False
        else:  self._rubberband.hide(); self._rubber_origin = None
        self._update_cursor()

    def _update_cursor(self):
        if self._pick_mode:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._label.setCursor(Qt.CursorShape.CrossCursor)
        elif self._crop_mode:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._label.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().unsetCursor(); self._label.unsetCursor()

    def color_at(self, lx: int, ly: int):
        """RGB at label coord (lx, ly), or None if outside the displayed pixmap."""
        pm = self._label.pixmap()
        if pm is None or pm.isNull(): return None
        ox = (self._label.width() - pm.width()) // 2
        oy = (self._label.height() - pm.height()) // 2
        px, py = lx - ox, ly - oy
        if not (0 <= px < pm.width() and 0 <= py < pm.height()): return None
        c = pm.toImage().pixelColor(px, py)
        return c.red(), c.green(), c.blue()

    def last_crop_rect(self) -> QRect | None:
        return self._last_crop_rect

    def crop_to_pixmap(self, label_rect: QRect) -> QPixmap | None:
        """Map a label-coord rect into the full-resolution `_pixmap` and copy."""
        label_pm = self._label.pixmap()
        if label_pm is None or label_pm.isNull() or self._pixmap is None: return None
        if label_pm.width() == 0 or label_pm.height() == 0: return None
        ox = (self._label.width() - label_pm.width()) // 2
        oy = (self._label.height() - label_pm.height()) // 2
        scale_x = self._pixmap.width()  / label_pm.width()
        scale_y = self._pixmap.height() / label_pm.height()
        sx = max(0, min(self._pixmap.width(),  round((label_rect.left() - ox) * scale_x)))
        sy = max(0, min(self._pixmap.height(), round((label_rect.top()  - oy) * scale_y)))
        w  = max(0, min(self._pixmap.width()  - sx, round(label_rect.width()  * scale_x)))
        h  = max(0, min(self._pixmap.height() - sy, round(label_rect.height() * scale_y)))
        if w <= 0 or h <= 0: return None
        return self._pixmap.copy(sx, sy, w, h)

    def eventFilter(self, obj, event):
        if obj is self._label and (self._pick_mode or self._crop_mode):
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                pt = event.position().toPoint()
                if self._pick_mode:
                    rgb = self.color_at(pt.x(), pt.y())
                    if rgb: self.color_picked.emit(*rgb, pt.x(), pt.y())
                    return True
                self._rubber_origin = pt
                self._rubberband.setGeometry(QRect(pt, QSize()))
                self._rubberband.show(); return True
            if et == QEvent.Type.MouseMove and self._crop_mode and self._rubber_origin:
                self._rubberband.setGeometry(
                    QRect(self._rubber_origin, event.position().toPoint()).normalized())
                return True
            if et == QEvent.Type.MouseButtonRelease and self._crop_mode and self._rubber_origin:
                self._last_crop_rect = self._rubberband.geometry()
                self._rubber_origin = None
                self.crop_selected.emit(self._last_crop_rect)
                return True
        return super().eventFilter(obj, event)

    # -- input ---------------------------------------------------------------

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit and self._pixmap is not None:
            self.fit_to_window()

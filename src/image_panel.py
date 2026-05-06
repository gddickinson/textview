"""Image-mode dock panel.

Hosts brightness / contrast / saturation / gamma sliders, a Reset button,
and a multi-frame navigator (Prev / spinbox / Next + "Frame X of N"
label) that controls the active `ImageView`.

The panel listens on `ImageView.loaded` to enable/disable the frame
controls based on whether the loaded file actually has multiple frames,
and on `ImageView.frame_changed` to keep its spinner in sync if the
frame is changed by some other UI element (keyboard nav, etc.).
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QFormLayout, QSlider, QLabel,
    QPushButton, QHBoxLayout, QSpinBox, QGroupBox, QFileDialog, QApplication,
    QCheckBox,
)


# Slider integer range → multiplier mapping. Brightness/contrast/saturation
# slide -100..+100 mapped to 0.0..2.0 (linear) — at 0 the slider centers on
# the identity (1.0). Gamma slides 1..300 mapped to 0.1..3.0 (centered at
# 100 → 1.0). Rounding-friendly so the value labels read cleanly.
_BCS_MIN, _BCS_MAX, _BCS_DEF = -100, 100, 0      # slider units
_GAMMA_MIN, _GAMMA_MAX, _GAMMA_DEF = 10, 300, 100


def _bcs_to_mult(v: int) -> float:
    return 1.0 + v / 100.0


def _mult_to_bcs(m: float) -> int:
    return int(round((m - 1.0) * 100))


def _gamma_to_mult(v: int) -> float:
    return v / 100.0


def _mult_to_gamma(m: float) -> int:
    return int(round(m * 100))


class ImagePanel(QDockWidget):
    """Right-side dock controlling image adjustments + frame navigation."""

    def __init__(self, image_view, parent=None):
        super().__init__("Image", parent)
        self.setObjectName("image_panel")
        self.image_view = image_view
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )

        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # -- adjustments group ---------------------------------------------
        adj_box = QGroupBox("Adjustments")
        adj_form = QFormLayout(adj_box)
        adj_form.setHorizontalSpacing(8)
        adj_form.setVerticalSpacing(4)

        self.s_brightness, self.l_brightness = self._make_bcs_slider()
        self.s_contrast,   self.l_contrast   = self._make_bcs_slider()
        self.s_saturation, self.l_saturation = self._make_bcs_slider()
        self.s_gamma,      self.l_gamma      = self._make_gamma_slider()

        adj_form.addRow("Brightness", self._wrap(self.s_brightness, self.l_brightness))
        adj_form.addRow("Contrast",   self._wrap(self.s_contrast,   self.l_contrast))
        adj_form.addRow("Saturation", self._wrap(self.s_saturation, self.l_saturation))
        adj_form.addRow("Gamma",      self._wrap(self.s_gamma,      self.l_gamma))

        self.cb_autoscale = QCheckBox("Autoscale (stretch min/max → 0/255)")
        self.cb_autoscale.setToolTip(
            "Linearly stretch each frame's actual pixel range across the "
            "full visible range. Default ON for 16-bit / float images "
            "(microscope TIFFs, GIS rasters), OFF for 8-bit photos.")
        adj_form.addRow(self.cb_autoscale)

        self.btn_reset = QPushButton("Reset adjustments")
        adj_form.addRow(self.btn_reset)
        outer.addWidget(adj_box)

        self.s_brightness.valueChanged.connect(self._on_brightness)
        self.s_contrast.valueChanged.connect(self._on_contrast)
        self.s_saturation.valueChanged.connect(self._on_saturation)
        self.s_gamma.valueChanged.connect(self._on_gamma)
        self.btn_reset.clicked.connect(self._on_reset)
        self.cb_autoscale.toggled.connect(self._on_autoscale_toggled)
        # Mirror state when ImageView's autoscale changes via load() default.
        self.image_view.autoscale_changed.connect(self._sync_autoscale)

        # -- frame navigation group ----------------------------------------
        self.frame_box = QGroupBox("Frames")
        nav = QHBoxLayout(self.frame_box)
        nav.setContentsMargins(6, 4, 6, 6)
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.spin_frame = QSpinBox()
        self.spin_frame.setMinimum(1); self.spin_frame.setMaximum(1)
        self.lbl_frame = QLabel("Frame 1 of 1")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.spin_frame)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        nav.addWidget(self.lbl_frame)
        outer.addWidget(self.frame_box)

        # -- pick / crop group --------------------------------------------
        self.pickcrop_box = QGroupBox("Pick / Crop")
        pc = QVBoxLayout(self.pickcrop_box)
        pc.setContentsMargins(6, 4, 6, 6)
        row1 = QHBoxLayout()
        self.btn_pick = QPushButton("Eyedropper"); self.btn_pick.setCheckable(True)
        self.swatch = QLabel(); self.swatch.setFixedSize(20, 20)
        self.swatch.setStyleSheet("border: 1px solid #888; background: transparent;")
        self.lbl_color = QLabel("—"); self.lbl_color.setMinimumWidth(80)
        row1.addWidget(self.btn_pick); row1.addWidget(self.swatch)
        row1.addWidget(self.lbl_color, 1)
        pc.addLayout(row1)
        row2 = QHBoxLayout()
        self.btn_crop = QPushButton("Crop region"); self.btn_crop.setCheckable(True)
        self.btn_save_crop = QPushButton("Save crop…"); self.btn_save_crop.setEnabled(False)
        row2.addWidget(self.btn_crop); row2.addWidget(self.btn_save_crop)
        pc.addLayout(row2)
        outer.addWidget(self.pickcrop_box)
        self.btn_pick.toggled.connect(self._on_pick_toggle)
        self.btn_crop.toggled.connect(self._on_crop_toggle)
        self.btn_save_crop.clicked.connect(self._save_crop)
        image_view.color_picked.connect(self._on_color_picked)
        image_view.crop_selected.connect(lambda _r: self.btn_save_crop.setEnabled(True))

        # -- histogram group ----------------------------------------------
        from .image_histogram import HistogramWidget
        self.hist_box = QGroupBox("Histogram")
        hbox = QVBoxLayout(self.hist_box)
        hbox.setContentsMargins(6, 4, 6, 6)
        self.histogram = HistogramWidget()
        hbox.addWidget(self.histogram)
        outer.addWidget(self.hist_box)
        # Re-draw the histogram on every adjustment / frame change.
        image_view.pixmap_updated.connect(
            lambda: self.histogram.update_for(image_view.current_adjusted_pil()))

        self.btn_prev.clicked.connect(lambda: self.image_view.step_frame(-1))
        self.btn_next.clicked.connect(lambda: self.image_view.step_frame(+1))
        self.spin_frame.valueChanged.connect(self._on_spin)

        outer.addStretch(1)
        self.setWidget(body)

        # Wire the view's signals
        image_view.loaded.connect(self._on_loaded)
        image_view.frame_changed.connect(self._on_frame_changed)

        # Default: disabled until an image with adjustments support is loaded.
        self._set_adjustments_enabled(False)
        self._set_frame_nav(1, 0)

    # -- slider construction --------------------------------------------------

    def _make_bcs_slider(self):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(_BCS_MIN, _BCS_MAX); s.setValue(_BCS_DEF)
        s.setTickPosition(QSlider.TickPosition.TicksBelow)
        s.setTickInterval(50)
        l = QLabel("1.00"); l.setMinimumWidth(40)
        return s, l

    def _make_gamma_slider(self):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(_GAMMA_MIN, _GAMMA_MAX); s.setValue(_GAMMA_DEF)
        s.setTickPosition(QSlider.TickPosition.TicksBelow)
        s.setTickInterval(50)
        l = QLabel("1.00"); l.setMinimumWidth(40)
        return s, l

    def _wrap(self, slider, label):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1); h.addWidget(label)
        return w

    # -- slider handlers ------------------------------------------------------

    def _on_brightness(self, v):
        m = _bcs_to_mult(v); self.l_brightness.setText(f"{m:.2f}")
        self.image_view.set_adjustment("brightness", m)

    def _on_contrast(self, v):
        m = _bcs_to_mult(v); self.l_contrast.setText(f"{m:.2f}")
        self.image_view.set_adjustment("contrast", m)

    def _on_saturation(self, v):
        m = _bcs_to_mult(v); self.l_saturation.setText(f"{m:.2f}")
        self.image_view.set_adjustment("saturation", m)

    def _on_gamma(self, v):
        m = _gamma_to_mult(v); self.l_gamma.setText(f"{m:.2f}")
        self.image_view.set_adjustment("gamma", m)

    def _on_reset(self):
        self._block(True)
        self.s_brightness.setValue(_BCS_DEF); self.l_brightness.setText("1.00")
        self.s_contrast.setValue(_BCS_DEF);   self.l_contrast.setText("1.00")
        self.s_saturation.setValue(_BCS_DEF); self.l_saturation.setText("1.00")
        self.s_gamma.setValue(_GAMMA_DEF);    self.l_gamma.setText("1.00")
        self._block(False)
        self.image_view.reset_adjustments()

    def _on_autoscale_toggled(self, on: bool):
        self.image_view.set_autoscale(on)

    def _sync_autoscale(self, on: bool):
        # ImageView decides its own default per file in `_load_with_pil`.
        # Mirror that into the checkbox without re-firing the toggle.
        self.cb_autoscale.blockSignals(True)
        self.cb_autoscale.setChecked(on)
        self.cb_autoscale.blockSignals(False)

    def _block(self, on: bool):
        for s in (self.s_brightness, self.s_contrast,
                  self.s_saturation, self.s_gamma):
            s.blockSignals(on)

    # -- frame nav handlers ---------------------------------------------------

    def _on_spin(self, v):
        # spinbox is 1-based; ImageView is 0-based.
        self.image_view.set_frame(v - 1)

    def _on_loaded(self, n_frames: int, has_adj: bool):
        self._set_adjustments_enabled(has_adj)
        self._set_frame_nav(n_frames, 0)
        # Reset the slider UI (values are already reset on the view side).
        self._on_reset() if has_adj else self._reset_sliders_visual()
        # Sync the autoscale checkbox to whatever load() decided per format.
        self._sync_autoscale(self.image_view.is_autoscale())

    def _on_frame_changed(self, idx: int):
        n = self.image_view.frame_count()
        self.spin_frame.blockSignals(True)
        self.spin_frame.setValue(idx + 1)
        self.spin_frame.blockSignals(False)
        self.lbl_frame.setText(f"Frame {idx + 1} of {n}")

    def _set_adjustments_enabled(self, on: bool):
        for w in (self.s_brightness, self.s_contrast, self.s_saturation,
                  self.s_gamma, self.btn_reset):
            w.setEnabled(on)

    def _set_frame_nav(self, n_frames: int, idx: int):
        multi = n_frames > 1
        self.frame_box.setEnabled(multi)
        self.spin_frame.blockSignals(True)
        self.spin_frame.setMinimum(1)
        self.spin_frame.setMaximum(max(1, n_frames))
        self.spin_frame.setValue(idx + 1)
        self.spin_frame.blockSignals(False)
        self.lbl_frame.setText(f"Frame {idx + 1} of {n_frames}")

    # -- pick / crop handlers -------------------------------------------------

    def _on_pick_toggle(self, on: bool):
        self.image_view.set_pick_mode(on)
        if on and self.btn_crop.isChecked():
            self.btn_crop.blockSignals(True); self.btn_crop.setChecked(False)
            self.btn_crop.blockSignals(False)

    def _on_crop_toggle(self, on: bool):
        self.image_view.set_crop_mode(on)
        if on and self.btn_pick.isChecked():
            self.btn_pick.blockSignals(True); self.btn_pick.setChecked(False)
            self.btn_pick.blockSignals(False)

    def _on_color_picked(self, r: int, g: int, b: int, _x: int, _y: int):
        hex_ = f"#{r:02X}{g:02X}{b:02X}"
        self.lbl_color.setText(f"{hex_}  ({r}, {g}, {b})")
        self.swatch.setStyleSheet(
            f"border: 1px solid #888; background: rgb({r}, {g}, {b});")
        QApplication.clipboard().setText(hex_)

    def _save_crop(self):
        rect = self.image_view.last_crop_rect()
        if rect is None: return
        pm = self.image_view.crop_to_pixmap(rect)
        if pm is None or pm.isNull(): return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save crop", "crop.png",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;All files (*)")
        if not path: return
        ok = pm.save(path)
        if ok:
            self.btn_save_crop.setEnabled(False)
            # Tell the parent window's status bar if available
            w = self.window()
            if hasattr(w, "statusBar"):
                w.statusBar().showMessage(f"Saved crop → {path}", 4000)

    def _reset_sliders_visual(self):
        self._block(True)
        self.s_brightness.setValue(_BCS_DEF); self.l_brightness.setText("1.00")
        self.s_contrast.setValue(_BCS_DEF);   self.l_contrast.setText("1.00")
        self.s_saturation.setValue(_BCS_DEF); self.l_saturation.setText("1.00")
        self.s_gamma.setValue(_GAMMA_DEF);    self.l_gamma.setText("1.00")
        self._block(False)

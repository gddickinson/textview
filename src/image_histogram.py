"""RGB histogram widget for the image dock.

Embeds a small `matplotlib` figure (the same `QtAgg` canvas the chart
dialog uses) and re-renders whenever a new image / adjustment lands.
Filled-area plots per channel — R/G/B for colour images, single grey
band for `L`-mode.

Theme-aware: re-reads palette `Base` (figure bg) and `Text` (axes /
ticks) on every redraw so it stays consistent across theme switches.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class HistogramWidget(QWidget):
    """Compact RGB / grayscale histogram. ~120 px tall."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        self.figure = Figure(figsize=(3.5, 1.4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFixedHeight(110)
        v.addWidget(self.canvas)
        self.lbl_summary = QLabel("(no image)")
        self.lbl_summary.setStyleSheet("color: #888; font-size: 10px;")
        v.addWidget(self.lbl_summary)

    def update_for(self, pil_image):
        """Re-render. `pil_image=None` clears the canvas."""
        bg = self.palette().color(QPalette.ColorRole.Base).name()
        fg = self.palette().color(QPalette.ColorRole.Text).name()
        self.figure.clear()
        self.figure.patch.set_facecolor(bg)
        if pil_image is None:
            self.canvas.draw(); self.lbl_summary.setText("(no image)")
            return
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(bg)
        for spine in ax.spines.values():
            spine.set_color(fg)
        ax.tick_params(colors=fg, labelsize=7)
        ax.set_xlim(0, 255)
        ax.set_yticks([])

        mode = pil_image.mode
        if mode == "L":
            hist = pil_image.histogram()[:256]
            ax.fill_between(range(256), hist, color="#aaaaaa", alpha=0.7)
            self.lbl_summary.setText(f"L · mean={_mean(hist):.0f}")
        else:
            rgb = pil_image.convert("RGB")
            bands = rgb.split()
            for band, color in zip(bands, ("#e74c3c", "#27ae60", "#2980b9")):
                hist = band.histogram()[:256]
                ax.fill_between(range(256), hist, color=color, alpha=0.45)
            means = [int(_mean(b.histogram()[:256])) for b in bands]
            self.lbl_summary.setText(
                f"RGB · means R={means[0]} G={means[1]} B={means[2]}")
        ax.set_xticks([0, 64, 128, 192, 255])
        self.canvas.draw()


def _mean(hist):
    """Mean intensity from a 256-bucket histogram."""
    total = sum(hist)
    if total == 0:
        return 0
    return sum(i * c for i, c in enumerate(hist)) / total

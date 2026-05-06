"""Reusable colour-picker widget.

A swatch button (click → `QColorDialog`) and a Reset button. Hex string
or empty for "use default". Emits `changed(str)` whenever the value is
set, so callers can wire into a `SettingsManager`.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QColorDialog,
)


class ColorPickerField(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, value: str = "", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
        self._btn = QPushButton(); self._btn.setFixedSize(120, 22)
        self._btn.clicked.connect(self._pick)
        reset = QPushButton("Reset"); reset.setFixedWidth(56)
        reset.clicked.connect(lambda: self.set_value(""))
        h.addWidget(self._btn); h.addWidget(reset); h.addStretch(1)
        self._value = ""
        self.set_value_silent(value)

    def value(self) -> str:
        return self._value

    def set_value(self, v: str):
        if (v or "") == self._value:
            return
        self._value = v or ""
        self._refresh()
        self.changed.emit(self._value)

    def set_value_silent(self, v: str):
        self._value = v or ""
        self._refresh()

    def _refresh(self):
        v = self._value
        if v:
            fg = "#000" if QColor(v).lightnessF() > 0.5 else "#fff"
            self._btn.setStyleSheet(
                f"QPushButton {{ background:{v}; border:1px solid #555; color:{fg}; }}")
            self._btn.setText(v)
        else:
            self._btn.setStyleSheet("")
            self._btn.setText("(theme default)")

    def _pick(self):
        c = QColorDialog.getColor(
            QColor(self._value or "#ffffff"), self, "Pick a colour")
        if c.isValid():
            self.set_value(c.name())

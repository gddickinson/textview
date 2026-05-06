"""Metadata dock widget.

Shows a grouped form of `(section, key, value)` rows produced by
`metadata.get_metadata`. Re-populates from scratch on each `update_for`
call (cheap; runs once per file open) and stays in sync with whatever
file the MainWindow currently has loaded.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QScrollArea,
)

from .metadata import get_metadata


class MetadataPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Metadata", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        self.setWidget(self._scroll)
        self.setMinimumWidth(300)
        self._show_empty()

    def update_for(self, path: str | None, fmt: str | None):
        self._clear()
        if not path or not fmt:
            self._show_empty()
            return
        sections = get_metadata(path, fmt)
        if not sections:
            self._show_empty("No metadata available")
            return
        for section, items in sections.items():
            self._layout.addWidget(self._build_section(section, items))
        self._layout.addStretch()

    # -- internals -----------------------------------------------------------

    def _build_section(self, name, items):
        g = QGroupBox(name)
        f = QFormLayout(g)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        f.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for key, value in items.items():
            label = QLabel(str(value))
            label.setWordWrap(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            f.addRow(f"{key}:", label)
        return g

    def _clear(self):
        # `deleteLater` is async — by itself it leaves the old widgets visible
        # until the next event-loop tick, which produces a brief overlap when
        # the next file is loaded. `setParent(None)` removes them from the
        # visible hierarchy immediately; deleteLater still tidies up.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _show_empty(self, message: str = "Open a file to see its metadata."):
        hint = QLabel(message)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; padding: 12px;")
        self._layout.addWidget(hint)
        self._layout.addStretch()

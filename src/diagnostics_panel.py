"""LSP diagnostics list panel.

A right-side `QDockWidget` that mirrors the diagnostics for the active
file as a sortable table (severity, line, column, source, message). Click
a row → editor cursor jumps to that line.

Populated by listening on `LSPController.notification_received` for
`textDocument/publishDiagnostics`. Also exposes `set_diagnostics(list)`
for tests / direct injection.
"""
from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget, QTableWidget, QTableWidgetItem, QHeaderView,
)


_SEV_LABEL = {1: "Error", 2: "Warn", 3: "Info", 4: "Hint"}
_SEV_COLOR = {1: "#e53935", 2: "#fb8c00", 3: "#039be5", 4: "#9e9e9e"}


class DiagnosticsPanel(QDockWidget):
    """Right-side dock listing diagnostics for the active file."""

    # Emitted when the user activates a row. Carries (line, character).
    jump_requested = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__("Diagnostics", parent)
        self.setObjectName("diagnostics_panel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Severity", "Line", "Col", "Message"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setWidget(self.table)
        self.table.itemActivated.connect(self._on_activated)
        self.table.cellDoubleClicked.connect(self._on_double_clicked)
        self._diagnostics: list[dict] = []

    def set_diagnostics(self, diagnostics: list[dict]):
        """Replace the table contents. Each diagnostic is the raw LSP dict."""
        diagnostics = list(diagnostics or [])
        # Sort by severity (Error first), then line, then character.
        def _key(d):
            sev = d.get("severity", 1)
            start = (d.get("range") or {}).get("start") or {}
            return (sev, start.get("line", 0), start.get("character", 0))
        diagnostics.sort(key=_key)
        self._diagnostics = diagnostics
        self.table.setRowCount(len(diagnostics))
        for row, d in enumerate(diagnostics):
            sev = d.get("severity", 1)
            start = (d.get("range") or {}).get("start") or {}
            line = int(start.get("line", 0))
            char = int(start.get("character", 0))
            sev_item = QTableWidgetItem(_SEV_LABEL.get(sev, "?"))
            from PyQt6.QtGui import QColor
            sev_item.setForeground(QColor(_SEV_COLOR.get(sev, "#888888")))
            self.table.setItem(row, 0, sev_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(line + 1)))
            self.table.setItem(row, 2, QTableWidgetItem(str(char + 1)))
            self.table.setItem(row, 3, QTableWidgetItem(str(d.get("message", ""))))
        self.setWindowTitle(f"Diagnostics ({len(diagnostics)})")

    def diagnostics(self) -> list[dict]:
        return list(self._diagnostics)

    def row_count(self) -> int:
        return self.table.rowCount()

    def _on_activated(self, item):
        self._emit_jump(item.row())

    def _on_double_clicked(self, row, _col):
        self._emit_jump(row)

    def _emit_jump(self, row: int):
        if 0 <= row < len(self._diagnostics):
            d = self._diagnostics[row]
            start = (d.get("range") or {}).get("start") or {}
            self.jump_requested.emit(int(start.get("line", 0)),
                                     int(start.get("character", 0)))

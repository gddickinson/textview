"""Per-column descriptive statistics for the open table.

Renders a `QTableView`-shaped grid: rows = columns of the source data,
columns = stats (count, missing, mean, median, stddev, min, Q1, Q3, max,
range, skew, kurtosis). For non-numeric columns the numeric cells are
blank and a "unique" + "top" pair is shown instead.

Respects the active filter — only currently-visible rows are summarised
(consistent with the chart dialog and the panel's selection stats).
"""
import math
from statistics import mean, median, pstdev, quantiles
from collections import Counter

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QPushButton, QLabel, QApplication,
)

from .table_data import (  # noqa: F401
    to_number, _NUMERIC_COLS, _STRING_COLS,
    numeric_stats as _numeric_stats, string_stats as _string_stats,
)


def column_stats(model, col_idx: int) -> dict:
    """One row of the stats table — numeric or string flavour."""
    n_rows = model.rowCount()
    raw = [model.get_value(r, col_idx) for r in range(n_rows)]
    missing = sum(1 for v in raw if v is None or v == "")
    is_num = model.numeric_columns()[col_idx] if 0 <= col_idx < model.columnCount() else False
    if is_num:
        nums = [to_number(v) for v in raw]
        nums = [n for n in nums if n is not None]
        s = _numeric_stats(nums)
    else:
        s = _string_stats([v for v in raw if v is not None])
    s["__missing__"] = str(missing)
    s["__numeric__"] = is_num
    return s


class _StatsModel(QAbstractTableModel):
    """Display-only model for the stats grid."""

    HEADERS = ["count", "missing", "mean", "median", "stddev",
               "min", "Q1", "Q3", "max", "range", "skew", "kurt",
               "unique", "top", "top_freq"]

    def __init__(self, source_model, parent=None):
        super().__init__(parent)
        self._cols = source_model.header()
        self._stats = [column_stats(source_model, c)
                       for c in range(source_model.columnCount())]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._cols)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= len(self._stats) or c >= len(self.HEADERS):
            return None
        s = self._stats[r]
        if role == Qt.ItemDataRole.DisplayRole:
            field = self.HEADERS[c]
            if field == "missing":
                return s.get("__missing__", "")
            return s.get(field, "")
        if role == Qt.ItemDataRole.TextAlignmentRole:
            field = self.HEADERS[c]
            # Numeric stats columns are right-aligned; text columns left.
            if field in {"top"}:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return self._cols[section] if 0 <= section < len(self._cols) else ""


class StatsDialog(QDialog):
    def __init__(self, source_model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Column statistics")
        self.resize(900, 380)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)
        info = QLabel(
            f"<i>Computed over {source_model.rowCount()} visible rows "
            f"of {source_model.total_rows()} total. Filtered rows are "
            f"excluded.</i>"
        )
        v.addWidget(info)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setModel(_StatsModel(source_model, self))
        self.table.resizeColumnsToContents()
        v.addWidget(self.table, 1)
        bar = QHBoxLayout()
        self.btn_copy = QPushButton("Copy as TSV")
        self.btn_copy.clicked.connect(self._copy_tsv)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        bar.addWidget(self.btn_copy); bar.addStretch(1); bar.addWidget(self.btn_close)
        v.addLayout(bar)

    def _copy_tsv(self):
        m = self.table.model()
        rows: list[str] = []
        rows.append("\t".join([""] + list(m.HEADERS)))
        for r in range(m.rowCount()):
            cells = [m.headerData(r, Qt.Orientation.Vertical) or ""]
            for c in range(m.columnCount()):
                cells.append(str(m.data(m.index(r, c)) or ""))
            rows.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(rows))

"""Spreadsheet-style view widget for delimited data.

Wraps `QTableView` with:
  - `load(text, has_header, delimiter)` — parses via `table_model` and
    populates the view.
  - Sortable headers (click to toggle asc/desc; numeric columns sort
    numerically thanks to `TableModel.sort`).
  - Selection-stats helper that summarises the current selection
    (count, numeric count, sum, avg, min, max) for the status bar.
  - Ctrl+C copies the selection as TSV to the clipboard so it can be
    pasted into another spreadsheet.
  - Knobs for grid / striped rows / font / row height / column-width
    cap, all driven from `view_styler.apply_table`.
  - Editable mode toggle that flips through to the underlying model.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QTableView, QHeaderView, QAbstractItemView, QApplication,
    QWidget, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
)

from .table_model import TableModel, parse_delimited, to_number


# Map UI labels → operator tokens that TableModel.set_filter understands.
_OP_LABELS = ["contains", ">", ">=", "<", "<=", "=", "≠"]
_OP_TO_TOKEN = {"contains": "~", "≠": "!="}


class TableFilterBar(QWidget):
    """Compact filter row above (or below) a `TableView`.

    Auto-applies as the user types — no Apply button. Uses the column /
    op / value triplet rather than a free-form expression so the syntax
    is discoverable without help text. `attach(table_view)` populates
    the column combobox from the bound model. Emits `filter_changed`
    on every reapply with `(visible, total)` so the host can update a
    status indicator.
    """

    filter_changed = pyqtSignal(int, int)  # visible_rows, total_rows

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        h.addWidget(QLabel("Filter:"))
        self.col = QComboBox(); self.col.setMinimumWidth(120)
        self.op = QComboBox(); self.op.addItems(_OP_LABELS); self.op.setMinimumWidth(80)
        self.value = QLineEdit(); self.value.setPlaceholderText("value")
        self.btn_clear = QPushButton("Clear")
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #888;")
        h.addWidget(self.col)
        h.addWidget(self.op)
        h.addWidget(self.value, 1)
        h.addWidget(self.btn_clear)
        h.addWidget(self.lbl_count)

        self._table: "TableView | None" = None
        self.col.currentIndexChanged.connect(self._reapply)
        self.op.currentTextChanged.connect(self._reapply)
        self.value.textChanged.connect(self._reapply)
        self.btn_clear.clicked.connect(self.reset)

    def attach(self, table_view: "TableView"):
        """Bind to a TableView whose model has just been populated."""
        self._table = table_view
        m = table_view.model()
        self.col.blockSignals(True)
        self.col.clear()
        if m is not None:
            self.col.addItems(m.header())
        self.col.blockSignals(False)
        self.reset()

    def reset(self):
        self.value.blockSignals(True)
        self.value.clear()
        self.value.blockSignals(False)
        if self._table and self._table.model() is not None:
            self._table.model().clear_filter()
            self._update_count()

    def _reapply(self):
        if not self._table:
            return
        m = self._table.model()
        if m is None:
            return
        col_idx = self.col.currentIndex()
        if col_idx < 0:
            return
        op_label = self.op.currentText()
        op = _OP_TO_TOKEN.get(op_label, op_label)
        value = self.value.text()
        if op == "~":
            # Empty substring → no filter; otherwise apply as-is.
            if not value:
                m.clear_filter()
            else:
                m.set_filter(col_idx, op, value)
        else:
            # Numeric / string compare needs a non-empty operand.
            if not value.strip():
                m.clear_filter()
            else:
                m.set_filter(col_idx, op, value)
        self._update_count()

    def _update_count(self):
        if not self._table or self._table.model() is None:
            self.lbl_count.setText("")
            return
        m = self._table.model()
        v, t = m.rowCount(), m.total_rows()
        self.lbl_count.setText(
            f"{v} / {t}" if m.has_filter() else f"{t} rows")
        self.filter_changed.emit(v, t)


class TableView(QTableView):
    """Spreadsheet view. `load(text)` populates it; `selection_stats()`
    returns a summary of the current selection."""

    selection_summary = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: TableModel | None = None
        self._max_col_width = 320

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setShowGrid(True)
        self.setFrameShape(self.Shape.NoFrame)

        h = self.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSortIndicatorShown(True)

        self.verticalHeader().setDefaultSectionSize(22)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

    # -- loading ------------------------------------------------------------

    def load(self, text: str, has_header: bool = True,
             delimiter: str | None = None) -> str:
        """Parse delimited text and bind the resulting model. Returns
        the delimiter actually used so the caller can echo it in the
        status bar / use it for save."""
        header, rows, used = parse_delimited(
            text, delimiter=delimiter, has_header=has_header,
        )
        self._model = TableModel(header, rows, parent=self)
        self.setModel(self._model)
        sm = self.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(self._on_selection_changed)
        self._auto_resize_columns()
        return used

    def _auto_resize_columns(self):
        if self._model is None:
            return
        self.resizeColumnsToContents()
        cap = self._max_col_width
        for c in range(self._model.columnCount()):
            if cap and self.columnWidth(c) > cap:
                self.setColumnWidth(c, cap)

    # -- selection ----------------------------------------------------------

    def selection_stats(self) -> dict:
        """Aggregate the current selection. Always returns a dict with
        `count` (cells); when at least one selected cell is numeric the
        result also includes `numeric`, `sum`, `avg`, `min`, `max`."""
        sm = self.selectionModel()
        if sm is None or self._model is None:
            return {"count": 0}
        idxs = sm.selectedIndexes()
        n = len(idxs)
        if n == 0:
            return {"count": 0}
        nums = []
        for idx in idxs:
            v = to_number(self._model.get_value(idx.row(), idx.column()))
            if v is not None:
                nums.append(v)
        out = {"count": n, "numeric": len(nums)}
        if nums:
            total = sum(nums)
            out.update(sum=total, avg=total / len(nums),
                       min=min(nums), max=max(nums))
        return out

    def _on_selection_changed(self, *_):
        self.selection_summary.emit(self.selection_stats())

    # -- copy as TSV --------------------------------------------------------

    def copy_selection_as_tsv(self) -> str:
        sm = self.selectionModel()
        if sm is None or self._model is None:
            return ""
        idxs = sorted(sm.selectedIndexes(),
                      key=lambda i: (i.row(), i.column()))
        if not idxs:
            return ""
        rows: dict[int, dict[int, str]] = {}
        for i in idxs:
            rows.setdefault(i.row(), {})[i.column()] = (
                self._model.get_value(i.row(), i.column())
            )
        out_lines = []
        for r in sorted(rows):
            cols = rows[r]
            lo, hi = min(cols), max(cols)
            line = "\t".join(cols.get(c, "") for c in range(lo, hi + 1))
            out_lines.append(line)
        return "\n".join(out_lines)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_C
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            text = self.copy_selection_as_tsv()
            if text:
                QApplication.clipboard().setText(text)
                event.accept()
                return
        super().keyPressEvent(event)

    # -- styling knobs ------------------------------------------------------

    def set_alternating_rows(self, on: bool):
        self.setAlternatingRowColors(on)

    def set_grid(self, on: bool):
        self.setShowGrid(on)

    def set_row_height(self, px: int):
        self.verticalHeader().setDefaultSectionSize(int(max(14, px)))

    def set_max_column_width(self, px: int):
        self._max_col_width = int(max(0, px))
        self._auto_resize_columns()

    def set_table_font(self, family: str, size: int):
        f = QFont(self.font())
        if family:
            f.setFamily(family)
        if size and size > 0:
            f.setPointSize(int(size))
        self.setFont(f)
        # Header font follows the body font.
        self.horizontalHeader().setFont(f)
        self.verticalHeader().setFont(f)

    # -- edit / serialize ---------------------------------------------------

    def set_editable(self, on: bool):
        if self._model is not None:
            self._model.set_editable(on)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
            if on else
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

    def is_editable(self) -> bool:
        return self.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers

    def serialize(self, delimiter: str = ",") -> str:
        return self._model.serialize(delimiter) if self._model else ""

    def has_model(self) -> bool:
        return self._model is not None

    def shape_label(self) -> str:
        if self._model is None:
            return ""
        return f"{self._model.rowCount()}×{self._model.columnCount()}"

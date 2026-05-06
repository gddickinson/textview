"""Pivot / group-by picker dialog.

The user picks Rows column, optional Cols column, Values column,
aggregator. **Generate** computes the result, writes it to a temp CSV,
and opens it in a new tab. The original table is preserved.
"""
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QGroupBox, QMessageBox,
)

from .table_pivot import pivot, to_csv, AGGS


class PivotDialog(QDialog):
    def __init__(self, model, window):
        super().__init__(window)
        self.setWindowTitle("Pivot / group-by")
        self.resize(420, 360)
        self.model = model
        self.window = window
        self._headers = model.header()

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)

        info = QLabel(
            f"<i>{model.rowCount()} visible rows of "
            f"{model.total_rows()} will be aggregated. "
            f"Result opens in a new tab.</i>")
        info.setWordWrap(True)
        v.addWidget(info)

        g = QGroupBox("Axes")
        f = QFormLayout(g)
        self.cb_rows = QComboBox()
        self.cb_rows.addItems(self._headers)
        f.addRow("Rows (group key):", self.cb_rows)
        self.cb_cols = QComboBox()
        self.cb_cols.addItem("(none — group-by only)", -1)
        for i, h in enumerate(self._headers):
            self.cb_cols.addItem(h, i)
        f.addRow("Cols (optional):", self.cb_cols)
        self.cb_values = QComboBox()
        # Numeric columns only for value (except for count, which any will do).
        numeric = self.model.numeric_columns()
        for i, h in enumerate(self._headers):
            label = h if numeric[i] else f"{h}  (non-numeric — count only)"
            self.cb_values.addItem(label, i)
        # Default to the first numeric column when one exists — a sum
        # over a string column needs the user to switch to count, which
        # is friction.
        for i, n in enumerate(numeric):
            if n:
                self.cb_values.setCurrentIndex(i); break
        f.addRow("Values:", self.cb_values)
        self.cb_agg = QComboBox()
        self.cb_agg.addItems(sorted(AGGS))
        self.cb_agg.setCurrentText("sum")
        f.addRow("Aggregator:", self.cb_agg)
        v.addWidget(g)

        # Tip
        v.addWidget(QLabel(
            "<small><i>Examples:<br>"
            "&nbsp;&nbsp;Rows=name, Cols=(none), Values=score, agg=mean → "
            "mean score per name<br>"
            "&nbsp;&nbsp;Rows=city, Cols=age, Values=score, agg=count → "
            "table of how many score points each (city, age) cell has"
            "</i></small>"))

        # Buttons
        bar = QHBoxLayout()
        self.btn_go = QPushButton("Generate")
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self._generate)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        bar.addStretch(1)
        bar.addWidget(self.btn_close); bar.addWidget(self.btn_go)
        v.addLayout(bar)

    def _generate(self):
        row_col = self.cb_rows.currentIndex()
        col_col = self.cb_cols.currentData()
        value_col = self.cb_values.currentData()
        agg = self.cb_agg.currentText()
        if col_col == -1:
            col_col = None
        try:
            header, rows = pivot(self.model, row_col, value_col, agg, col_col)
        except ValueError as e:
            QMessageBox.warning(self, "Pivot", str(e))
            return
        if not rows:
            QMessageBox.information(self, "Pivot",
                                    "No rows produced — check filter / values.")
            return
        # Write to a temp CSV and open in a new tab
        out_dir = Path(tempfile.gettempdir()) / "textview_pivots"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = f"{header[0]}_{agg}".replace(" ", "_")
        out = out_dir / f"pivot_{tag}.csv"
        out.write_text(to_csv(header, rows), encoding="utf-8")
        self.window.api.open(str(out))
        self.accept()

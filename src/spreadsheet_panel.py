"""Right-side dock that drives the active table.

Contains four sections:
  - **Selection stats** — count, sum, avg, min, max, median, stddev
    (median + stddev are computed here from the model's get_value;
    `TableView.selection_summary` only carries the simpler stats).
  - **Edit** — toggle whether cells are editable. When on,
    double-click / typing a key starts an edit.
  - **Insert / delete** — buttons that operate on the current selection's
    rows / columns.
  - **Charts** — opens `PlotDialog` against the current model.

The panel listens on `TableView.selection_summary` for live updates and
on `TableView.model().modelReset` for re-loads.
"""
from statistics import median, pstdev

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QGroupBox, QCheckBox, QPushButton, QMessageBox, QInputDialog,
)

from .table_model import to_number
from .plot_dialog import PlotDialog
from .stats_dialog import StatsDialog
from .pivot_dialog import PivotDialog


class SpreadsheetPanel(QDockWidget):
    """Dock with selection stats + edit toggle + insert/delete + charts."""

    def __init__(self, table_view, parent=None):
        super().__init__("Spreadsheet", parent)
        self.setObjectName("spreadsheet_panel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.table_view = table_view

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        v.addWidget(self._stats_group())
        v.addWidget(self._edit_group())
        v.addWidget(self._insert_delete_group())
        v.addWidget(self._chart_group())
        v.addStretch(1)
        self.setWidget(body)

        # Live update on selection change.
        self.table_view.selection_summary.connect(self._on_selection)
        self._refresh_enabled()

    # -- groups -------------------------------------------------------------

    def _stats_group(self) -> QGroupBox:
        g = QGroupBox("Selection")
        f = QFormLayout(g)
        self.lbl_count = QLabel("—")
        self.lbl_sum = QLabel("—")
        self.lbl_avg = QLabel("—")
        self.lbl_min = QLabel("—")
        self.lbl_max = QLabel("—")
        self.lbl_median = QLabel("—")
        self.lbl_stddev = QLabel("—")
        f.addRow("Cells:",   self.lbl_count)
        f.addRow("Sum:",     self.lbl_sum)
        f.addRow("Average:", self.lbl_avg)
        f.addRow("Min:",     self.lbl_min)
        f.addRow("Max:",     self.lbl_max)
        f.addRow("Median:",  self.lbl_median)
        f.addRow("Std dev:", self.lbl_stddev)
        return g

    def _edit_group(self) -> QGroupBox:
        g = QGroupBox("Edit")
        v = QVBoxLayout(g)
        self.cb_editable = QCheckBox("Cells editable (double-click to edit)")
        self.cb_editable.toggled.connect(self._on_edit_toggled)
        v.addWidget(self.cb_editable)
        return g

    def _insert_delete_group(self) -> QGroupBox:
        g = QGroupBox("Insert / Delete")
        v = QVBoxLayout(g)
        row1 = QHBoxLayout()
        self.btn_row_above = QPushButton("Insert row above")
        self.btn_row_below = QPushButton("Insert row below")
        row1.addWidget(self.btn_row_above); row1.addWidget(self.btn_row_below)
        row2 = QHBoxLayout()
        self.btn_del_rows = QPushButton("Delete selected rows")
        row2.addWidget(self.btn_del_rows)
        row3 = QHBoxLayout()
        self.btn_col_left = QPushButton("Insert column ←")
        self.btn_col_right = QPushButton("Insert column →")
        row3.addWidget(self.btn_col_left); row3.addWidget(self.btn_col_right)
        row4 = QHBoxLayout()
        self.btn_del_cols = QPushButton("Delete selected columns")
        row4.addWidget(self.btn_del_cols)
        for r in (row1, row2, row3, row4):
            v.addLayout(r)
        self.btn_row_above.clicked.connect(lambda: self._insert_row(-1))
        self.btn_row_below.clicked.connect(lambda: self._insert_row(+1))
        self.btn_del_rows.clicked.connect(self._delete_rows)
        self.btn_col_left.clicked.connect(lambda: self._insert_col(-1))
        self.btn_col_right.clicked.connect(lambda: self._insert_col(+1))
        self.btn_del_cols.clicked.connect(self._delete_cols)
        return g

    def _chart_group(self) -> QGroupBox:
        g = QGroupBox("Analysis")
        v = QVBoxLayout(g)
        self.btn_stats = QPushButton("Column statistics…")
        self.btn_stats.clicked.connect(self._open_stats)
        v.addWidget(self.btn_stats)
        self.btn_derive = QPushButton("Add derived column…")
        self.btn_derive.clicked.connect(self._add_derived)
        v.addWidget(self.btn_derive)
        self.btn_pivot = QPushButton("Pivot / group-by…")
        self.btn_pivot.clicked.connect(self._open_pivot)
        v.addWidget(self.btn_pivot)
        self.btn_plot = QPushButton("New chart…")
        self.btn_plot.clicked.connect(self._open_plot)
        v.addWidget(self.btn_plot)
        v.addWidget(QLabel("<i>All three honour the active filter.</i>"))
        return g

    def _add_derived(self):
        m = self.table_view.model()
        if m is None:
            QMessageBox.information(self, "Derived column", "Open a CSV first.")
            return
        name, ok = QInputDialog.getText(
            self, "Derived column",
            "Column name (Python identifier):",
            text="new_col")
        if not ok or not name.strip():
            return
        formula, ok = QInputDialog.getText(
            self, "Derived column",
            f"Formula for '{name}'.\n"
            f"Available variables: {', '.join(h for h in m.header() if h.isidentifier())}\n"
            f"Functions: log, sqrt, exp, abs, min, max, round, …",
            text="")
        if not ok or not formula.strip():
            return
        ok, msg = m.add_derived_column(name.strip(), formula.strip())
        if not ok:
            QMessageBox.warning(self, "Derived column", msg)
        else:
            # Make the new column visible if the view scrolled past it.
            self.table_view.scrollTo(m.index(0, m.columnCount() - 1))

    def _open_stats(self):
        m = self.table_view.model()
        if m is None or m.rowCount() == 0:
            QMessageBox.information(self, "Statistics", "Open a CSV first.")
            return
        StatsDialog(m, self).exec()

    def _open_pivot(self):
        m = self.table_view.model()
        if m is None or m.rowCount() == 0:
            QMessageBox.information(self, "Pivot", "Open a CSV first.")
            return
        # Walk up to the MainWindow so PivotDialog can call api.open
        # without needing to know the panel's parent depth.
        mw = self.window()
        PivotDialog(m, mw).exec()

    # -- selection-driven stats --------------------------------------------

    def _on_selection(self, stats: dict):
        m = self.table_view.model()
        sm = self.table_view.selectionModel()
        if not stats or not stats.get("count") or m is None or sm is None:
            for lbl in (self.lbl_count, self.lbl_sum, self.lbl_avg,
                        self.lbl_min, self.lbl_max,
                        self.lbl_median, self.lbl_stddev):
                lbl.setText("—")
            return
        self.lbl_count.setText(str(stats["count"]))
        if stats.get("numeric"):
            self.lbl_sum.setText(f"{stats['sum']:g}")
            self.lbl_avg.setText(f"{stats['avg']:g}")
            self.lbl_min.setText(f"{stats['min']:g}")
            self.lbl_max.setText(f"{stats['max']:g}")
            # Median / stddev — recompute from selection.
            nums = []
            for idx in sm.selectedIndexes():
                v = to_number(m.get_value(idx.row(), idx.column()))
                if v is not None:
                    nums.append(v)
            self.lbl_median.setText(f"{median(nums):g}" if nums else "—")
            self.lbl_stddev.setText(f"{pstdev(nums):g}"
                                    if len(nums) > 1 else "—")
        else:
            for lbl in (self.lbl_sum, self.lbl_avg, self.lbl_min,
                        self.lbl_max, self.lbl_median, self.lbl_stddev):
                lbl.setText("—")

    # -- edit toggle --------------------------------------------------------

    def _on_edit_toggled(self, on: bool):
        self.table_view.set_editable(on)

    # -- insert / delete ----------------------------------------------------

    def _selected_view_rows(self) -> list[int]:
        sm = self.table_view.selectionModel()
        if sm is None:
            return []
        return sorted({i.row() for i in sm.selectedIndexes()})

    def _selected_view_cols(self) -> list[int]:
        sm = self.table_view.selectionModel()
        if sm is None:
            return []
        return sorted({i.column() for i in sm.selectedIndexes()})

    def _insert_row(self, direction: int):
        m = self.table_view.model()
        if m is None:
            return
        rows = self._selected_view_rows()
        anchor = rows[0] if rows and direction == -1 else (rows[-1] if rows else None)
        # Above = insert before the first selected → after_view_row=anchor-1
        # Below = insert after the last selected → after_view_row=anchor
        after = (anchor - 1) if direction == -1 and anchor is not None else anchor
        m.insert_row(after_view_row=after)
        self._refresh_enabled()

    def _delete_rows(self):
        m = self.table_view.model()
        if m is None:
            return
        rows = self._selected_view_rows()
        if not rows:
            QMessageBox.information(self, "Delete rows",
                                    "Select at least one row first.")
            return
        if QMessageBox.question(
                self, "Delete rows",
                f"Delete {len(rows)} row(s)? This cannot be undone.",
        ) != QMessageBox.StandardButton.Yes:
            return
        m.delete_rows(rows)
        self._refresh_enabled()

    def _insert_col(self, direction: int):
        m = self.table_view.model()
        if m is None:
            return
        cols = self._selected_view_cols()
        anchor = cols[0] if cols and direction == -1 else (cols[-1] if cols else None)
        if anchor is None:
            at = m.columnCount()  # append to end
        else:
            at = anchor if direction == -1 else anchor + 1
        m.insert_column(at=at, name=f"col {m.columnCount() + 1}")
        self._refresh_enabled()

    def _delete_cols(self):
        m = self.table_view.model()
        if m is None:
            return
        cols = self._selected_view_cols()
        if not cols:
            QMessageBox.information(self, "Delete columns",
                                    "Select at least one column first.")
            return
        if QMessageBox.question(
                self, "Delete columns",
                f"Delete {len(cols)} column(s)? This cannot be undone.",
        ) != QMessageBox.StandardButton.Yes:
            return
        m.delete_columns(cols)
        self._refresh_enabled()

    # -- chart --------------------------------------------------------------

    def _open_plot(self):
        m = self.table_view.model()
        if m is None or m.rowCount() == 0:
            QMessageBox.information(self, "Plot",
                                    "Open a CSV file first.")
            return
        dlg = PlotDialog(m, self)
        dlg.exec()

    # -- public -------------------------------------------------------------

    def refresh_for_model(self):
        """Call this after the host loads / clears a model so the panel
        controls reflect the new state (enabled vs. disabled, editability
        checkbox in the right position)."""
        self._refresh_enabled()

    def _refresh_enabled(self):
        m = self.table_view.model()
        has_model = m is not None
        for w in (self.cb_editable, self.btn_row_above, self.btn_row_below,
                  self.btn_del_rows, self.btn_col_left, self.btn_col_right,
                  self.btn_del_cols, self.btn_plot, self.btn_stats,
                  self.btn_derive, self.btn_pivot):
            w.setEnabled(has_model)
        # Reflect current editability state on the checkbox without
        # re-firing the toggled signal.
        self.cb_editable.blockSignals(True)
        self.cb_editable.setChecked(self.table_view.is_editable())
        self.cb_editable.blockSignals(False)

"""Charting dialog backed by matplotlib's QtAgg canvas.

Opens with the columns of the active `TableModel` populated as picker
options. The user picks chart type → X column → one or more Y columns
(via checkboxes), tweaks title / axis labels, and hits Plot. The figure
renders into an embedded `FigureCanvasQTAgg` with the standard
NavigationToolbar (pan / zoom / save).

Only **visible** rows are plotted, so an active filter is honoured.

Chart types and column requirements:
    Line       X numeric (or categorical → indexed), Y numeric (≥ 1)
    Bar        X any (used as labels), Y numeric (≥ 1)
    Scatter    X numeric, Y numeric (≥ 1)
    Histogram  Y numeric (≥ 1) — X ignored
    Pie        X any (labels), Y numeric (exactly 1)
    Box        Y numeric (≥ 1) — X ignored
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QPushButton, QGroupBox, QCheckBox, QLabel, QFileDialog, QMessageBox,
    QScrollArea, QWidget,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT,
)
from matplotlib.figure import Figure

from .table_model import TableModel, to_number
from . import plot_overlays as ov


_CHART_TYPES = [
    "Line", "Bar", "Scatter", "Histogram", "Pie", "Box",
    "Heatmap", "Correlation matrix", "Dual axis",
]
# Trendlines and reference lines apply to these chart types.
_OVERLAY_CHARTS = {"Line", "Scatter", "Bar"}


class PlotDialog(QDialog):
    def __init__(self, model: TableModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot")
        self.resize(900, 640)
        self.model = model

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Left column: pickers.
        sidebar = self._build_sidebar()
        outer.addWidget(sidebar, 0)

        # Right column: figure + toolbar.
        right = QVBoxLayout()
        self.figure = Figure(figsize=(6, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        right.addWidget(self.toolbar, 0)
        right.addWidget(self.canvas, 1)
        wrap = QWidget(); wrap.setLayout(right)
        outer.addWidget(wrap, 1)

    # -- sidebar UI ---------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(280)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(8)

        # Type
        type_group = QGroupBox("Chart")
        type_form = QFormLayout(type_group)
        self.combo_type = QComboBox(); self.combo_type.addItems(_CHART_TYPES)
        type_form.addRow("Type:", self.combo_type)
        v.addWidget(type_group)

        # X column
        x_group = QGroupBox("X axis")
        xf = QFormLayout(x_group)
        self.combo_x = QComboBox()
        self.combo_x.addItem("(row index)", -1)
        for i, name in enumerate(self.model.header()):
            self.combo_x.addItem(name, i)
        xf.addRow("Column:", self.combo_x)
        v.addWidget(x_group)

        # Y columns (multi via checkboxes)
        y_group = QGroupBox("Y values (numeric)")
        yl = QVBoxLayout(y_group)
        self.y_checks: list[tuple[int, QCheckBox]] = []
        numeric_cols = self.model.numeric_columns()
        any_numeric = False
        for i, name in enumerate(self.model.header()):
            cb = QCheckBox(name)
            if not numeric_cols[i]:
                cb.setEnabled(False)
                cb.setText(f"{name}  (non-numeric)")
            else:
                any_numeric = True
            yl.addWidget(cb)
            self.y_checks.append((i, cb))
        if not any_numeric:
            yl.addWidget(QLabel("<i>No numeric columns detected.</i>"))
        v.addWidget(y_group)

        # Labels
        lbl_group = QGroupBox("Labels (optional)")
        lf = QFormLayout(lbl_group)
        self.le_title = QLineEdit()
        self.le_xlabel = QLineEdit()
        self.le_ylabel = QLineEdit()
        lf.addRow("Title:", self.le_title)
        lf.addRow("X label:", self.le_xlabel)
        lf.addRow("Y label:", self.le_ylabel)
        v.addWidget(lbl_group)

        # Analysis overlays (trendlines, reference lines, axis scales, labels)
        ana_group = QGroupBox("Analysis (Line / Scatter / Bar)")
        af = QFormLayout(ana_group)
        self.combo_trend = QComboBox(); self.combo_trend.addItems(ov.TREND_TYPES)
        af.addRow("Trendline:", self.combo_trend)
        self.cb_show_eq = QCheckBox("Show fit equation + R²"); self.cb_show_eq.setChecked(True)
        af.addRow(self.cb_show_eq)
        self.cb_mean = QCheckBox("Mean reference line")
        self.cb_median = QCheckBox("Median reference line")
        af.addRow(self.cb_mean); af.addRow(self.cb_median)
        self.cb_logx = QCheckBox("Log X")
        self.cb_logy = QCheckBox("Log Y")
        af.addRow(self.cb_logx); af.addRow(self.cb_logy)
        self.cb_data_labels = QCheckBox("Data labels")
        af.addRow(self.cb_data_labels)
        v.addWidget(ana_group)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_plot = QPushButton("Plot")
        self.btn_save = QPushButton("Save image…")
        btn_row.addWidget(self.btn_plot); btn_row.addWidget(self.btn_save)
        v.addLayout(btn_row)
        v.addStretch(1)

        scroll.setWidget(body)
        self.btn_plot.clicked.connect(self._plot)
        self.btn_save.clicked.connect(self._save_image)
        return scroll

    # -- data extraction ----------------------------------------------------

    def _selected_y_indices(self) -> list[int]:
        return [i for i, cb in self.y_checks if cb.isChecked() and cb.isEnabled()]

    def _column_values(self, col_idx: int) -> list[str]:
        n = self.model.rowCount()
        return [self.model.get_value(r, col_idx) for r in range(n)]

    def _numeric_column(self, col_idx: int) -> list[float]:
        out = []
        for v in self._column_values(col_idx):
            n = to_number(v)
            out.append(float("nan") if n is None else n)
        return out

    # -- plot ---------------------------------------------------------------

    def _plot(self):
        chart = self.combo_type.currentText()
        y_idxs = self._selected_y_indices()
        # Correlation matrix uses all numeric columns automatically; Pie
        # accepts a single Y; everything else needs ≥ 1 Y.
        if not y_idxs and chart not in ("Pie", "Correlation matrix"):
            QMessageBox.information(self, "Plot",
                                    "Pick at least one numeric Y column.")
            return
        x_idx = self.combo_x.currentData()  # -1 means row index
        header = self.model.header()
        n = self.model.rowCount()
        if n == 0:
            QMessageBox.information(self, "Plot", "No rows to plot.")
            return

        self.figure.clear()
        # Match the figure to the parent widget's palette so the chart
        # doesn't look like a glaring white sheet inside a dark theme.
        from PyQt6.QtGui import QPalette
        pal_bg = self.palette().color(QPalette.ColorRole.Base).name()
        pal_fg = self.palette().color(QPalette.ColorRole.Text).name()
        self.figure.patch.set_facecolor(pal_bg)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(pal_bg)
        for spine in ax.spines.values(): spine.set_color(pal_fg)
        ax.tick_params(colors=pal_fg)
        ax.xaxis.label.set_color(pal_fg)
        ax.yaxis.label.set_color(pal_fg)
        ax.title.set_color(pal_fg)

        if chart == "Histogram":
            self._draw_hist(ax, y_idxs)
        elif chart == "Box":
            self._draw_box(ax, y_idxs)
        elif chart == "Pie":
            self._draw_pie(ax, x_idx, y_idxs)
        elif chart == "Heatmap":
            self._draw_heatmap(ax, x_idx, y_idxs)
        elif chart == "Correlation matrix":
            self._draw_corr_matrix(ax)
        elif chart == "Dual axis":
            self._draw_dual_axis(ax, x_idx, y_idxs)
        else:
            self._draw_xy(ax, chart, x_idx, y_idxs)

        if self.le_title.text(): ax.set_title(self.le_title.text())
        if self.le_xlabel.text(): ax.set_xlabel(self.le_xlabel.text())
        elif x_idx >= 0 and chart not in ("Histogram", "Box", "Pie"):
            ax.set_xlabel(header[x_idx])
        if self.le_ylabel.text(): ax.set_ylabel(self.le_ylabel.text())
        elif len(y_idxs) == 1 and chart not in ("Pie",):
            ax.set_ylabel(header[y_idxs[0]])

        self.figure.tight_layout()
        self.canvas.draw()

    def _draw_xy(self, ax, chart, x_idx, y_idxs):
        header = self.model.header()
        if x_idx >= 0:
            x_raw = self._column_values(x_idx)
            x_num = [to_number(v) for v in x_raw]
            x_is_numeric = all(v is not None for v in x_num)
        else:
            x_raw, x_num, x_is_numeric = [], [], False

        n_series = len(y_idxs)
        for i, yi in enumerate(y_idxs):
            ys = self._numeric_column(yi)
            label = header[yi]
            xs_for_overlay = x_num if x_is_numeric else list(range(len(ys)))
            if chart == "Line":
                xs = x_num if x_is_numeric else list(range(len(ys)))
                ax.plot(xs, ys, marker="o", label=label)
            elif chart == "Bar":
                positions = [k + i / n_series * 0.8 for k in range(len(ys))]
                ax.bar(positions, ys, width=0.8 / n_series, label=label)
            elif chart == "Scatter":
                if not x_is_numeric:
                    QMessageBox.warning(self, "Plot",
                                        "Scatter requires a numeric X column.")
                    return
                ax.scatter(x_num, ys, label=label)
            self._apply_trendline(ax, xs_for_overlay, ys, label)
            if self.cb_data_labels.isChecked() and chart != "Bar":
                self._annotate_points(ax, xs_for_overlay, ys)

        # Reference lines computed across the union of selected Y values.
        all_y = [v for yi in y_idxs for v in self._numeric_column(yi)]
        for ref_label, level in ov.reference_levels(all_y,
                mean=self.cb_mean.isChecked(), median=self.cb_median.isChecked()):
            ax.axhline(level, color="#888", linestyle=":", linewidth=1.2,
                       label=ref_label)

        if chart == "Bar" and x_raw:
            ax.set_xticks([k + (n_series - 1) / n_series * 0.4
                           for k in range(len(x_raw))])
            ax.set_xticklabels(x_raw, rotation=45, ha="right")
        elif chart == "Line" and x_raw and not x_is_numeric:
            ax.set_xticks(range(len(x_raw)))
            ax.set_xticklabels(x_raw, rotation=45, ha="right")

        if self.cb_logx.isChecked():
            try: ax.set_xscale("log")
            except ValueError: pass
        if self.cb_logy.isChecked():
            try: ax.set_yscale("log")
            except ValueError: pass

        if n_series > 1 or chart in ("Line", "Scatter") \
                or self.cb_mean.isChecked() or self.cb_median.isChecked() \
                or self.combo_trend.currentText() != ov.TREND_NONE:
            ax.legend()
        ax.grid(True, alpha=0.3)

    def _draw_hist(self, ax, y_idxs):
        header = self.model.header()
        for yi in y_idxs:
            data = [v for v in self._numeric_column(yi) if v == v]
            ax.hist(data, bins="auto", alpha=0.6, label=header[yi])
        if len(y_idxs) > 1:
            ax.legend()
        ax.grid(True, alpha=0.3)

    def _draw_box(self, ax, y_idxs):
        header = self.model.header()
        data = [[v for v in self._numeric_column(i) if v == v] for i in y_idxs]
        ax.boxplot(data, tick_labels=[header[i] for i in y_idxs])
        ax.grid(True, alpha=0.3, axis="y")

    def _draw_pie(self, ax, x_idx, y_idxs):
        if x_idx < 0:
            QMessageBox.warning(self, "Plot",
                                "Pie chart needs an X (label) column.")
            return
        if len(y_idxs) != 1:
            QMessageBox.warning(self, "Plot",
                                "Pie chart needs exactly one Y column.")
            return
        labels = self._column_values(x_idx)
        values = self._numeric_column(y_idxs[0])
        clean = [(L, v) for L, v in zip(labels, values) if v == v and v > 0]
        if not clean:
            QMessageBox.warning(self, "Plot", "No positive numeric values.")
            return
        ax.pie([v for _, v in clean], labels=[L for L, _ in clean],
               autopct="%1.1f%%", startangle=90)
        ax.set_aspect("equal")

    def _apply_trendline(self, ax, xs, ys, series_label: str):
        """Fit and draw the trendline chosen in the Analysis group, if any."""
        kind = self.combo_trend.currentText()
        if kind == ov.TREND_NONE: return
        out = ov.trendline(kind, xs, ys)
        if out is None: return
        x_line, y_line, params, r2 = out
        if self.cb_show_eq.isChecked():
            eq = ov.equation_text(kind, params)
            r2_str = f"  (R²={r2:.3f})" if r2 is not None else ""
            label = f"{series_label} · {kind.lower()}: {eq}{r2_str}"
        else:
            label = f"{series_label} · {kind.lower()}"
        ax.plot(x_line, y_line, "--", linewidth=1.4, label=label)

    def _annotate_points(self, ax, xs, ys):
        for x, y in zip(xs, ys):
            if y == y:  # skip NaN
                ax.annotate(f"{y:.3g}", (x, y), textcoords="offset points",
                            xytext=(4, 4), fontsize=8, color=ax.xaxis.label.get_color())

    def _draw_heatmap(self, ax, x_idx, y_idxs):
        """2D heatmap of selected numeric columns × visible rows.

        Each cell coloured by value. X axis labels come from the X
        column (or row index). The colour scale spans the union of
        selected Y columns so different series are comparable.
        """
        if not y_idxs:
            QMessageBox.warning(self, "Plot",
                                "Pick at least one numeric Y column.")
            return
        import numpy as np
        header = self.model.header()
        rows = self.model.rowCount()
        labels = (self._column_values(x_idx) if x_idx >= 0
                  else [str(i) for i in range(rows)])
        data = np.array([self._numeric_column(yi) for yi in y_idxs])
        im = ax.imshow(data, aspect="auto", cmap="viridis")
        # Thin labels when there are too many to read at typical figure
        # widths — show every Nth and leave the rest blank.
        stride = max(1, rows // 25)
        ax.set_xticks(range(0, rows, stride))
        ax.set_xticklabels([labels[i] for i in range(0, rows, stride)],
                           rotation=45, ha="right")
        ax.set_yticks(range(len(y_idxs)))
        ax.set_yticklabels([header[i] for i in y_idxs])
        # Annotate cells if grid is small enough to be readable.
        if rows * len(y_idxs) <= 80:
            for i in range(len(y_idxs)):
                for j in range(rows):
                    v = data[i, j]
                    if not np.isnan(v):
                        ax.text(j, i, f"{v:.3g}",
                                ha="center", va="center", fontsize=8,
                                color="white" if v < np.nanmean(data) else "black")
        self.figure.colorbar(im, ax=ax, shrink=0.8)

    def _draw_corr_matrix(self, ax):
        """Pairwise Pearson correlation across all numeric columns of
        the visible data. Plotted as a -1..+1 heatmap with values."""
        import numpy as np
        header = self.model.header()
        nums = self.model.numeric_columns()
        cols = [i for i, n in enumerate(nums) if n]
        if len(cols) < 2:
            QMessageBox.warning(self, "Plot",
                                "Correlation needs ≥ 2 numeric columns.")
            return
        data = np.array([self._numeric_column(c) for c in cols])
        # Drop columns where variance is 0 (constant) — corrcoef would NaN.
        var_ok = [i for i in range(data.shape[0])
                  if not np.isnan(data[i]).all() and np.nanvar(data[i]) > 0]
        if len(var_ok) < 2:
            QMessageBox.warning(self, "Plot",
                                "Need ≥ 2 columns with non-zero variance.")
            return
        keep = data[var_ok]
        names = [header[cols[i]] for i in var_ok]
        # Use np.ma to handle NaNs gracefully.
        masked = np.ma.masked_invalid(keep)
        corr = np.ma.corrcoef(masked).filled(np.nan)
        im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha="right")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        for i in range(len(names)):
            for j in range(len(names)):
                v = corr[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}",
                            ha="center", va="center", fontsize=9,
                            color="black" if abs(v) < 0.6 else "white")
        self.figure.colorbar(im, ax=ax, shrink=0.8)

    def _draw_dual_axis(self, ax, x_idx, y_idxs):
        """Two Y series on shared X with independent scales — useful
        when units differ (sales vs headcount, age vs score)."""
        if len(y_idxs) != 2:
            QMessageBox.warning(self, "Plot",
                                "Dual axis needs exactly 2 numeric Y "
                                "columns (got %d)." % len(y_idxs))
            return
        header = self.model.header()
        if x_idx >= 0:
            xs_raw = self._column_values(x_idx)
            xs_num = [to_number(v) for v in xs_raw]
            x_is_numeric = all(v is not None for v in xs_num)
        else:
            xs_raw, xs_num, x_is_numeric = [], [], False

        y1_idx, y2_idx = y_idxs
        ys1 = self._numeric_column(y1_idx)
        ys2 = self._numeric_column(y2_idx)
        ax2 = ax.twinx()
        # Match the secondary axis to the figure theme.
        from PyQt6.QtGui import QPalette
        fg = self.palette().color(QPalette.ColorRole.Text).name()
        ax2.tick_params(colors=fg)
        ax2.spines["right"].set_color(fg)

        x_for_plot = xs_num if x_is_numeric else list(range(len(ys1)))
        c1, c2 = "#3b8eea", "#e74c3c"
        l1, = ax.plot(x_for_plot, ys1, color=c1, marker="o",
                      label=header[y1_idx])
        l2, = ax2.plot(x_for_plot, ys2, color=c2, marker="s", linestyle="--",
                       label=header[y2_idx])
        ax.set_ylabel(header[y1_idx], color=c1)
        ax2.set_ylabel(header[y2_idx], color=c2)
        ax.tick_params(axis="y", labelcolor=c1)
        ax2.tick_params(axis="y", labelcolor=c2)
        if not x_is_numeric and xs_raw:
            ax.set_xticks(range(len(xs_raw)))
            ax.set_xticklabels(xs_raw, rotation=45, ha="right")
        ax.legend(handles=[l1, l2], loc="best")
        ax.grid(True, alpha=0.3)

    def _save_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart as", "chart.png",
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if path:
            self.figure.savefig(path, dpi=150, bbox_inches="tight")

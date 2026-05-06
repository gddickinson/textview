"""Modal file-formats database browser.

Two-pane dialog: a search/filter box and category list on the left,
a rendered detail pane on the right. Triggered from Help → File
formats database… (Ctrl+Shift+D)."""
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit, QTextBrowser, QLabel, QComboBox, QPushButton, QSplitter,
    QWidget,
)

from .format_db import db, FormatEntry


class FormatDBDialog(QDialog):
    def __init__(self, parent=None, *, prefilter_extension: str = ""):
        super().__init__(parent)
        self.setWindowTitle("File formats database")
        self.resize(1000, 660)

        self._db = db()

        # -- top filter row --------------------------------------------------
        self.search = QLineEdit(); self.search.setPlaceholderText(
            "Search by name / extension / tag (e.g. 'parquet', 'image', "
            "'compressed', '.pdf')…")
        self.category = QComboBox()
        self.category.addItem("All categories", "")
        for cat, n in self._db.categories().items():
            self.category.addItem(f"{cat}  ({n})", cat)
        top = QHBoxLayout(); top.addWidget(QLabel("Filter:"))
        top.addWidget(self.search, 3); top.addWidget(self.category, 1)

        # -- list / detail panes --------------------------------------------
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget::item{padding:4px;}")
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list); splitter.addWidget(self.detail)
        splitter.setSizes([320, 680])

        self.count_label = QLabel("")
        self.close_btn = QPushButton("Close")
        bottom = QHBoxLayout()
        bottom.addWidget(self.count_label); bottom.addStretch(1)
        bottom.addWidget(self.close_btn)

        root = QVBoxLayout(self)
        root.addLayout(top); root.addWidget(splitter, 1); root.addLayout(bottom)

        # -- wire --------------------------------------------------------
        self.search.textChanged.connect(self._refresh)
        self.category.currentIndexChanged.connect(self._refresh)
        self.list.currentItemChanged.connect(self._on_select)
        self.close_btn.clicked.connect(self.accept)

        # Optional: pre-seed the search field so opening the dialog from a
        # specific file lands directly on its entry.
        if prefilter_extension:
            self.search.setText(prefilter_extension)

        self._refresh()

    # ----------------------------------------------------------- behavior --

    def _refresh(self):
        q = self.search.text().strip()
        cat = self.category.currentData()
        if q:
            entries = self._db.search(q, limit=200)
        else:
            entries = sorted(self._db.entries, key=lambda e: e.name.lower())
        if cat:
            entries = [e for e in entries if e.category == cat]
        self.list.clear()
        for e in entries:
            item = QListWidgetItem(e.summary())
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            item.setToolTip(e.description[:240])
            self.list.addItem(item)
        self.count_label.setText(
            f"{len(entries)} format{'s' if len(entries) != 1 else ''} "
            f"of {len(self._db.entries)} total")
        if self.list.count() > 0: self.list.setCurrentRow(0)
        else: self.detail.setMarkdown("*(no matches — try a broader search)*")

    def _on_select(self, current, _previous):
        if current is None: return
        entry = self._db.by_id.get(current.data(Qt.ItemDataRole.UserRole))
        if entry is not None:
            self.detail.setMarkdown(entry.to_markdown())


def show_format_db(window, *, ext: str = ""):
    """Convenience launcher — opens the dialog as a child of `window`,
    optionally pre-filtered by extension."""
    dlg = FormatDBDialog(window, prefilter_extension=ext)
    dlg.exec()

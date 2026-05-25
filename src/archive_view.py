"""Tree-view archive browser.

QSplitter holding a `QTreeView` (member list) and a `QTextBrowser`
preview pane. Selecting a member loads its first ~1 MB of text into
the preview when the member looks textual; binary members show a
short summary instead. Double-click prompts for an extract location.

Backed by `archive_loader` which handles ZIP / TAR / 7z. The previous
markdown TOC remains available as the rendered-view alternative —
Ctrl+T flips between the tree and the markdown.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter, QTreeView, QTextBrowser, QFileDialog,
    QMessageBox, QAbstractItemView, QHeaderView, QSizePolicy,
)

from .archive_loader import (
    list_members, extract_member, ArchiveReadError, Member,
)


# Members beyond this size show only a summary, not the body text.
_PREVIEW_BYTE_CAP = 1_000_000
# File extensions that are safe to preview as text.
_TEXT_EXTS = {
    ".txt", ".log", ".rst", ".md", ".markdown", ".html", ".htm", ".xml",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".tsv",
    ".py", ".pyi", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".c", ".h",
    ".cpp", ".hpp", ".java", ".rb", ".sh", ".bash", ".css", ".sql",
    ".conf", ".env", ".gitignore", ".dockerignore", ".editorconfig",
}


class ArchiveView(QWidget):
    """Tree-view + preview pane for the active archive."""

    # Emits the on-disk path of a successfully-extracted member so the
    # host can offer to open it.
    member_extracted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: str | None = None
        self._members: list[Member] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal, self)

        self.tree = QTreeView(split)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSortingEnabled(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.activated.connect(self._on_activated)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        self.preview = QTextBrowser(split)
        self.preview.setFrameShape(self.preview.Shape.NoFrame)
        self.preview.setOpenExternalLinks(True)

        split.addWidget(self.tree)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)

        self.tree.selectionModel  # NB: model attached in `load()`

    # ----------------------------------------------------------- public --

    def clear(self) -> None:
        self._path = None
        self._members = []
        self.tree.setModel(QStandardItemModel())
        self.preview.setHtml("")

    def load(self, path: str) -> bool:
        """Populate the tree from the archive at `path`. Returns False on
        a read error (the host can fall back to the markdown TOC)."""
        try:
            self._members = list_members(path)
        except ArchiveReadError as e:
            self.clear()
            self.preview.setHtml(f"<p><b>Error:</b> {e}</p>")
            return False
        self._path = path
        model = self._build_tree_model(self._members)
        self.tree.setModel(model)
        self.tree.setHeaderHidden(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, model.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        # Sort directories first, then alphabetical.
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._show_summary_preview()
        # Connect after model is attached — the model changes each load.
        self.tree.selectionModel().currentChanged.connect(
            lambda cur, _prev: self._on_selection(cur))
        return True

    # ----------------------------------------------------------- internals --

    def _build_tree_model(self, members: list[Member]) -> QStandardItemModel:
        """Build a tree model: directories collapse children below them.

        Paths use `/` as the separator; we walk each part and create
        intermediate directory nodes on demand."""
        model = QStandardItemModel(self)
        model.setHorizontalHeaderLabels(["Name", "Size", "Modified", "Type"])
        # Map directory path → node (for nested lookups).
        node_for_path: dict[str, QStandardItem] = {"": model.invisibleRootItem()}

        # Helper to add a row under a parent node.
        def add_row(parent: QStandardItem, name: str, size_label: str,
                    when: str, type_label: str,
                    full_path: str, is_dir: bool) -> QStandardItem:
            icon = "📁 " if is_dir else "📄 "
            n = QStandardItem(icon + name)
            n.setData(full_path, role=Qt.ItemDataRole.UserRole)
            n.setData(is_dir, role=Qt.ItemDataRole.UserRole + 1)
            s = QStandardItem(size_label)
            s.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            w = QStandardItem(when)
            t = QStandardItem(type_label)
            for it in (s, w, t): it.setEditable(False)
            n.setEditable(False)
            parent.appendRow([n, s, w, t])
            return n

        # Sort members so parents come before children (deterministic walk).
        for m in sorted(members, key=lambda x: x.name):
            parts = m.name.rstrip("/").split("/")
            # Walk every parent path, creating placeholder directory nodes
            # if the archive didn't include explicit dir entries.
            cur_path = ""
            parent = node_for_path[""]
            for i, part in enumerate(parts):
                is_last = (i == len(parts) - 1)
                cur_path = f"{cur_path}/{part}" if cur_path else part
                if cur_path in node_for_path:
                    parent = node_for_path[cur_path]
                    continue
                size_label = "—" if (not is_last or m.is_dir) else _humansize(m.size)
                when = (datetime.fromtimestamp(m.mtime).strftime("%Y-%m-%d %H:%M")
                        if (is_last and m.mtime) else "")
                ext = Path(part).suffix.lower()
                type_label = ("directory" if (not is_last or m.is_dir)
                              else ext or "file")
                node = add_row(parent, part, size_label, when, type_label,
                               m.name, (not is_last or m.is_dir))
                node_for_path[cur_path] = node
                parent = node
        return model

    def _on_selection(self, current_index) -> None:
        if not current_index.isValid():
            self._show_summary_preview(); return
        model = current_index.model()
        # Column 0 holds the full path in UserRole.
        sibling = model.index(current_index.row(), 0, current_index.parent())
        full_path = sibling.data(Qt.ItemDataRole.UserRole) or ""
        is_dir = bool(sibling.data(Qt.ItemDataRole.UserRole + 1))
        if not full_path or is_dir:
            self._show_summary_preview(); return
        self._preview_member(full_path)

    def _on_activated(self, _index) -> None:
        # Activated = Enter on the keyboard. Same as double-click: extract.
        self._extract_current()

    def _on_double_clicked(self, _index) -> None:
        self._extract_current()

    def _extract_current(self) -> None:
        idx = self.tree.currentIndex()
        if not idx.isValid() or not self._path: return
        sibling = idx.model().index(idx.row(), 0, idx.parent())
        full_path = sibling.data(Qt.ItemDataRole.UserRole) or ""
        is_dir = bool(sibling.data(Qt.ItemDataRole.UserRole + 1))
        if is_dir or not full_path: return
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Extract to folder", str(Path(self._path).parent))
        if not dest_dir: return
        try:
            out = extract_member(self._path, full_path, dest_dir)
        except ArchiveReadError as e:
            QMessageBox.warning(self, "Extract failed", str(e))
            return
        self.member_extracted.emit(out)

    def _preview_member(self, member_name: str) -> None:
        """Show a textual preview of a member, capped to 1 MB. Binary
        members get a one-line summary."""
        if self._path is None: return
        info = next((m for m in self._members if m.name == member_name), None)
        if info is None:
            self._show_summary_preview(); return

        ext = Path(member_name).suffix.lower()
        looks_text = ext in _TEXT_EXTS
        if info.size > _PREVIEW_BYTE_CAP:
            self.preview.setHtml(
                f"<p><b>{_esc(member_name)}</b></p>"
                f"<p>{_humansize(info.size)} — too large to preview "
                f"(cap {_humansize(_PREVIEW_BYTE_CAP)}). "
                f"Double-click to extract.</p>"
            )
            return
        if not looks_text:
            self.preview.setHtml(
                f"<p><b>{_esc(member_name)}</b></p>"
                f"<p>{_humansize(info.size)} · "
                f"{ext or '(no extension)'} · binary preview suppressed. "
                f"Double-click to extract.</p>"
            )
            return
        # Pull just this member's bytes out of the archive — reuse
        # extract_member to a temp file? No — for text we want it in
        # memory. Use zipfile / tarfile directly for the preview path.
        try:
            text = _read_member_text(self._path, member_name)
        except Exception as e:
            self.preview.setHtml(
                f"<p><b>{_esc(member_name)}</b></p>"
                f"<p>Could not read for preview: {_esc(str(e))}</p>"
            )
            return
        # Tiny wrapper so the preview is selectable + monospace.
        self.preview.setHtml(
            f"<p><b>{_esc(member_name)}</b> · {_humansize(info.size)} · "
            f"<i>Double-click to extract.</i></p>"
            f"<pre style='font-family: Menlo, Consolas, monospace; "
            f"font-size: 11pt; white-space: pre-wrap;'>"
            f"{_esc(text)}</pre>"
        )

    def _show_summary_preview(self) -> None:
        if not self._path or not self._members:
            self.preview.setHtml("")
            return
        files = [m for m in self._members if not m.is_dir]
        total = sum(m.size for m in files)
        name = Path(self._path).name
        self.preview.setHtml(
            f"<h2>{_esc(name)}</h2>"
            f"<p>{len(files):,} files · {_humansize(total)} total uncompressed</p>"
            f"<p><i>Click a file in the tree to preview, "
            f"or double-click to extract.</i></p>"
        )


# ----------------------------------------------------------- helpers --

def _read_member_text(path: str, member_name: str) -> str:
    """Return the first 1 MB of `member_name` as text. Uses zipfile /
    tarfile directly instead of an extract-to-disk to avoid disk I/O
    on a preview."""
    import zipfile, tarfile
    suffix = Path(path).name.lower()
    if suffix.endswith((".zip", ".jar", ".war", ".apk", ".ipa")):
        with zipfile.ZipFile(path) as zf:
            data = zf.read(member_name)
    elif (suffix.endswith(".tar") or ".tar." in suffix
          or suffix.endswith((".tgz", ".tbz2", ".txz", ".tb2"))):
        with tarfile.open(path, "r:*") as tf:
            f = tf.extractfile(member_name)
            data = f.read() if f else b""
    elif suffix.endswith(".7z"):
        import py7zr  # may raise ImportError → caller catches
        with py7zr.SevenZipFile(path, mode="r") as sz:
            extracted = sz.read(targets=[member_name]) or {}
            data = next(iter(extracted.values())).read() if extracted else b""
    else:
        data = b""
    data = data[:_PREVIEW_BYTE_CAP]
    return data.decode("utf-8", errors="replace")


def _humansize(n: int) -> str:
    if n < 0: return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))

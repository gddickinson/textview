"""Cmd/Ctrl+P quick-open palette.

Fuzzy-finds files under the active project root (or the current file's
folder if no project is set). Reuses the ranker from `command_palette`.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
)

from .command_palette import fuzzy_score


# Skip these directories when indexing — every project has them and they
# blow the file count up by orders of magnitude.
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
    "build", ".next", ".idea", ".vscode", "target",
}
_MAX_FILES = 8000


def _index_root(window) -> Path | None:
    """Pick the project root, current-file folder, or home — in that order."""
    pp = getattr(window, "project_panel", None)
    if pp is not None:
        root = pp._model.rootPath() if pp._model else ""
        if root and Path(root).is_dir():
            return Path(root)
    if window._current_path:
        p = Path(window._current_path).parent
        if p.is_dir():
            return p
    return None


def _walk(base: Path) -> list[Path]:
    out: list[Path] = []
    for path in base.rglob("*"):
        # Drop anything inside a skipped directory.
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.relative_to(base).parts):
            continue
        if path.is_file():
            out.append(path)
            if len(out) >= _MAX_FILES:
                out.append(Path("__truncated__"))
                break
    return out


def show_quick_open(window):
    """Modal entry point used by the Ctrl+P shortcut."""
    dlg = build_quick_open(window)
    if dlg is not None:
        dlg.exec()


def build_quick_open(window):
    """Construct the dialog without `exec`'ing it. Returns the QDialog,
    or None when there are no files to show (status-bar message
    already emitted)."""
    base = _index_root(window)
    if base is None:
        window.statusBar().showMessage(
            "Open a folder first (Ctrl+Shift+O) or a file.", 3000)
        return None
    files = _walk(base)
    if not files:
        window.statusBar().showMessage(f"No files in {base}.", 3000)
        return None

    dlg = QDialog(window); dlg.setWindowTitle(f"Quick open — {base}")
    dlg.setModal(True); dlg.resize(680, 460)
    v = QVBoxLayout(dlg); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)
    inp = QLineEdit(); inp.setPlaceholderText("Type to filter files…")
    v.addWidget(inp)
    lst = QListWidget(); v.addWidget(lst, 1)

    # Pre-compute relative-path strings once.
    rels = [(p, str(p.relative_to(base))) for p in files
            if p.name != "__truncated__"]
    truncated = any(p.name == "__truncated__" for p in files)

    def populate(query: str):
        lst.clear()
        if not query:
            for p, rel in rels[:200]:
                item = QListWidgetItem(rel)
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                lst.addItem(item)
        else:
            scored = []
            for p, rel in rels:
                # Heavy weight on the basename, lighter on the full path.
                s = fuzzy_score(query, p.name) * 2 + max(0, fuzzy_score(query, rel))
                if s > 0:
                    scored.append((s, rel, p))
            scored.sort(key=lambda x: -x[0])
            for _s, rel, p in scored[:200]:
                item = QListWidgetItem(rel)
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                lst.addItem(item)
        if truncated:
            tail = QListWidgetItem(f"…{_MAX_FILES} file cap reached; refine your query")
            tail.setFlags(Qt.ItemFlag.NoItemFlags)
            lst.addItem(tail)
        if lst.count():
            for i in range(lst.count()):
                if lst.item(i).flags() & Qt.ItemFlag.ItemIsSelectable:
                    lst.setCurrentRow(i); break

    populate("")
    inp.textChanged.connect(populate)

    def trigger():
        item = lst.currentItem()
        if item is None: return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            dlg.accept()
            window.open_file(path)

    inp.returnPressed.connect(trigger)
    lst.itemActivated.connect(lambda _: trigger())

    QShortcut(QKeySequence("Down"), inp, activated=lambda: lst.setCurrentRow(
        min(lst.count() - 1, lst.currentRow() + 1)))
    QShortcut(QKeySequence("Up"), inp, activated=lambda: lst.setCurrentRow(
        max(0, lst.currentRow() - 1)))
    inp.setFocus()
    return dlg

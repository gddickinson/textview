"""Find-in-project (Ctrl+Shift+F).

Modal that walks the active project root for text matches across files,
streaming hits into a `QListWidget`. Click → opens the file at that line.
Reuses `quick_open._SKIP_DIRS` and `_index_root` so the same "what counts
as the project" logic applies.

The search itself is line-oriented and synchronous (per file), but yields
to the event loop after every file via `QApplication.processEvents()` so
the UI stays responsive on large trees. Capped at 5000 hits to avoid
runaway memory; the cap shows up as a status line.
"""
from __future__ import annotations
import fnmatch
import re
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QCheckBox, QLabel, QPushButton,
)

from .quick_open import _SKIP_DIRS, _index_root


_MAX_HITS = 5000
_MAX_FILE_BYTES = 2_000_000   # skip files bigger than this — log files etc.


def _walk_files(base: Path):
    """Yield text files under `base`, skipping noise dirs and giant files."""
    for path in base.rglob("*"):
        rel = path.relative_to(base)
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel.parts):
            continue
        if not path.is_file(): continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES: continue
        except OSError:
            continue
        yield path


def search_in_file(path: Path, pattern, case_sensitive: bool, max_hits: int):
    """Return list of (line_number_1_based, line_text) for hits in this file."""
    out: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for i, line in enumerate(text.splitlines(), start=1):
        haystack = line if case_sensitive else line.lower()
        if isinstance(pattern, re.Pattern):
            if pattern.search(line): out.append((i, line.rstrip()))
        else:
            if pattern in haystack: out.append((i, line.rstrip()))
        if len(out) >= max_hits: break
    return out


def compile_pattern(query: str, *, regex: bool, case: bool):
    """Return a `re.Pattern` for regex mode, or a plain string for literal.
    Returns None if regex is requested but malformed."""
    if regex:
        flags = 0 if case else re.IGNORECASE
        try: return re.compile(query, flags)
        except re.error: return None
    return query if case else query.lower()


def file_matches_glob(path: Path, base: Path, pattern: str) -> bool:
    """`pattern` is a comma-separated glob list. Empty matches everything."""
    pattern = (pattern or "").strip()
    if not pattern: return True
    rel = str(path.relative_to(base))
    name = path.name
    for p in (s.strip() for s in pattern.split(",") if s.strip()):
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p):
            return True
    return False


def show_workspace_search(window):
    base = _index_root(window)
    if base is None:
        window.statusBar().showMessage("No project root — open a folder first.", 4000); return

    dlg = QDialog(window); dlg.setWindowTitle(f"Find in {base.name}")
    dlg.setModal(True); dlg.resize(720, 520)
    v = QVBoxLayout(dlg); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)

    row1 = QHBoxLayout()
    inp = QLineEdit(); inp.setPlaceholderText("Search…")
    cb_re = QCheckBox(".*"); cb_re.setToolTip("Regular expression")
    cb_case = QCheckBox("Aa"); cb_case.setToolTip("Match case")
    row1.addWidget(inp, 1); row1.addWidget(cb_re); row1.addWidget(cb_case)
    v.addLayout(row1)

    row2 = QHBoxLayout()
    glob = QLineEdit(); glob.setPlaceholderText("Files (glob, e.g. *.py, src/**/*.ts) — blank = all")
    row2.addWidget(QLabel("Files:")); row2.addWidget(glob, 1)
    v.addLayout(row2)

    lst = QListWidget(); v.addWidget(lst, 1)
    status = QLabel(""); v.addWidget(status)

    def run_search():
        lst.clear()
        q = inp.text()
        if not q: status.setText(""); return
        pat = compile_pattern(q, regex=cb_re.isChecked(), case=cb_case.isChecked())
        if pat is None: status.setText("Bad regex"); return
        glob_pat = glob.text()
        n_files = n_hits = 0
        for path in _walk_files(base):
            if not file_matches_glob(path, base, glob_pat): continue
            n_files += 1
            hits = search_in_file(path, pat, cb_case.isChecked(), _MAX_HITS - n_hits)
            for line_no, line in hits:
                rel = path.relative_to(base)
                item = QListWidgetItem(f"{rel}:{line_no}: {line[:200]}")
                item.setData(Qt.ItemDataRole.UserRole, (str(path), line_no))
                lst.addItem(item); n_hits += 1
            if n_hits >= _MAX_HITS:
                status.setText(f"Cap reached: {n_hits} hits across {n_files} files."); return
            if n_files % 25 == 0: QApplication.processEvents()
        status.setText(f"{n_hits} hits across {n_files} files.")

    inp.returnPressed.connect(run_search)
    btn = QPushButton("Search"); btn.clicked.connect(run_search); v.addWidget(btn)

    def open_hit(item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        path, line_no = data
        dlg.accept(); window.open_file(path)
        from PyQt6.QtGui import QTextCursor
        c = window.viewer.code.textCursor(); c.movePosition(QTextCursor.MoveOperation.Start)
        c.movePosition(QTextCursor.MoveOperation.Down, n=line_no - 1)
        window.viewer.code.setTextCursor(c); window.viewer.code.centerCursor()

    lst.itemActivated.connect(open_hit)
    QShortcut(QKeySequence("Escape"), dlg, activated=dlg.reject)
    inp.setFocus()
    dlg.exec()

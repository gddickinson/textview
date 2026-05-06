"""Persistent snippet library.

JSON-backed store at `~/.config/TextView/snippets.json`. A snippet is a
name + body + optional language tag + optional list of free-form tags.
Inserted at cursor via `Ctrl+;` picker; "Save selection as snippet…"
captures the active editor selection.

Trust boundary: snippet names match `[A-Za-z][A-Za-z0-9_-]{0,63}` so a
malicious name can never be used as a path component or escape into a
shell command.
"""
from __future__ import annotations
import json, re, time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
DEFAULT_PATH = Path.home() / ".config" / "TextView" / "snippets.json"


def is_valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


@dataclass
class Snippet:
    name: str
    body: str
    language: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Snippet":
        return Snippet(
            name=str(d.get("name", "")),
            body=str(d.get("body", "")),
            language=str(d.get("language", "")),
            tags=list(d.get("tags") or []),
            created_at=float(d.get("created_at") or time.time()),
        )

    def search_blob(self) -> str:
        """Concatenated indexable text — for the fuzzy picker."""
        return " ".join([self.name, self.language, " ".join(self.tags),
                         self.body[:200]])


class SnippetStore:
    """Atomic-ish JSON file store."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self._cache: dict[str, Snippet] | None = None

    def _load(self) -> dict[str, Snippet]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = {}; return self._cache
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._cache = {}; return self._cache
        out: dict[str, Snippet] = {}
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict): continue
            name = item.get("name")
            if not isinstance(name, str) or not is_valid_name(name): continue
            out[name] = Snippet.from_dict(item)
        self._cache = out
        return out

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        items = [s.to_dict() for s in (self._cache or {}).values()]
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[Snippet]:
        return sorted(self._load().values(), key=lambda s: s.name.lower())

    def get(self, name: str) -> Snippet | None:
        return self._load().get(name)

    def save(self, snippet: Snippet) -> Snippet:
        if not is_valid_name(snippet.name):
            raise ValueError(f"invalid snippet name: {snippet.name!r}")
        self._load()[snippet.name] = snippet
        self._save()
        return snippet

    def delete(self, name: str) -> bool:
        cache = self._load()
        if name not in cache: return False
        del cache[name]; self._save(); return True

    def search(self, query: str) -> list[tuple[int, Snippet]]:
        """Fuzzy-rank snippets by query; returns (score, snippet) descending."""
        from .command_palette import fuzzy_score
        out: list[tuple[int, Snippet]] = []
        for s in self.list():
            sc = fuzzy_score(query, s.search_blob())
            if sc >= 0:
                out.append((sc, s))
        out.sort(key=lambda x: -x[0])
        return out


# ----------------------------------------------------------- UI -----------

def show_snippet_picker(window):
    """Modal `Ctrl+;` picker — fuzzy-filter snippets and insert at cursor."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QShortcut, QKeySequence
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel,
    )
    store = window.snippets if hasattr(window, "snippets") else SnippetStore()
    snippets = store.list()
    if not snippets:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(window, "No snippets",
            'No snippets yet. Use "Save selection as snippet…" to create one.')
        return

    dlg = QDialog(window); dlg.setWindowTitle("Insert snippet"); dlg.setModal(True)
    dlg.resize(560, 420)
    v = QVBoxLayout(dlg); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)
    inp = QLineEdit(); inp.setPlaceholderText("Filter by name / tag / body…")
    v.addWidget(inp)
    lst = QListWidget(); v.addWidget(lst, 1)
    preview = QLabel(); preview.setWordWrap(True)
    preview.setStyleSheet("color: #888; font-family: monospace;")
    preview.setMinimumHeight(80); preview.setMaximumHeight(140)
    v.addWidget(preview)

    def populate(q: str):
        lst.clear()
        rows = store.search(q) if q else [(0, s) for s in snippets]
        for _, s in rows[:300]:
            tag_str = f" [{', '.join(s.tags)}]" if s.tags else ""
            label = f"{s.name}{tag_str}"
            if s.language: label += f"  · {s.language}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s.name)
            lst.addItem(item)
        if lst.count(): lst.setCurrentRow(0)

    def update_preview():
        item = lst.currentItem()
        if item is None: preview.setText(""); return
        s = store.get(item.data(Qt.ItemDataRole.UserRole))
        if s: preview.setText(s.body[:500])

    populate(""); update_preview()
    inp.textChanged.connect(populate)
    lst.currentRowChanged.connect(lambda _: update_preview())

    def insert():
        item = lst.currentItem()
        if item is None: return
        s = store.get(item.data(Qt.ItemDataRole.UserRole))
        if s is None: return
        dlg.accept()
        cv = window.viewer.code
        if cv.isReadOnly():
            window.statusBar().showMessage(
                "Enable Edit mode (Ctrl+E) to insert snippets.", 4000)
            return
        cv.textCursor().insertText(s.body)

    inp.returnPressed.connect(insert)
    lst.itemActivated.connect(lambda _: insert())
    QShortcut(QKeySequence("Down"), inp,
        activated=lambda: lst.setCurrentRow(min(lst.count() - 1, lst.currentRow() + 1)))
    QShortcut(QKeySequence("Up"), inp,
        activated=lambda: lst.setCurrentRow(max(0, lst.currentRow() - 1)))
    inp.setFocus()
    dlg.exec()


def save_selection_as_snippet(window):
    """Capture the current editor selection (or whole buffer) into a snippet."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    cv = window.viewer.code
    cursor = cv.textCursor()
    body = cursor.selectedText().replace(" ", "\n")  # QTextCursor uses U+2029
    if not body:
        body = cv.toPlainText()
    if not body.strip():
        QMessageBox.information(window, "Empty selection",
            "Nothing to save — make a selection first or open a file.")
        return
    name, ok = QInputDialog.getText(window, "Save snippet",
        "Name (letters, digits, _, -; ≤64 chars):")
    if not ok or not name: return
    if not is_valid_name(name):
        QMessageBox.warning(window, "Bad name",
            f"Name {name!r} is invalid. Allowed: [A-Za-z][A-Za-z0-9_-]{{0,63}}")
        return
    tags_str, ok = QInputDialog.getText(window, "Tags",
        "Optional tags, comma-separated:")
    tags = [t.strip() for t in (tags_str or "").split(",") if t.strip()] if ok else []
    lang = window._current_format if getattr(window, "_current_format", None) else ""
    store = window.snippets if hasattr(window, "snippets") else SnippetStore()
    store.save(Snippet(name=name, body=body, language=lang, tags=tags))
    window.statusBar().showMessage(f"Saved snippet → {name}", 4000)

"""Fuzzy command palette.

Modal dialog that lists every available QAction with its shortcut. Type
to filter (substring + simple character-subsequence fuzzy match);
Enter triggers the selected action; Esc dismisses. Mirrors VS Code's
Cmd/Ctrl+K behavior.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
)


def fuzzy_score(query: str, text: str) -> int:
    """Tiny character-subsequence ranker. Higher is better; -1 means miss.

    Big bonuses for prefix and contiguous runs; penalty per skipped char.
    """
    q, t = query.lower(), text.lower()
    if not q:
        return 0
    if t.startswith(q):
        return 1000 + len(q)
    if q in t:
        return 500 + len(q) - t.find(q)
    qi = ti = 0
    score = 0
    last_match = -2
    while qi < len(q) and ti < len(t):
        if q[qi] == t[ti]:
            score += 5
            if ti == last_match + 1:
                score += 6   # contiguous
            last_match = ti
            qi += 1
        ti += 1
    if qi < len(q):
        return -1
    return score - (len(t) - last_match) // 4


def show_command_palette(window):
    """Modal entry point — what the action shortcut calls."""
    dlg = build_command_palette(window)
    dlg.exec()


def build_command_palette(window):
    """Constructs the dialog without `exec`'ing it. Lets the screenshot
    harness capture the populated palette without blocking."""
    actions = []
    for menu_action in window.menuBar().actions():
        sub = menu_action.menu()
        if sub is None:
            continue
        _collect(sub, actions, prefix=menu_action.text().replace("&", ""))

    dlg = QDialog(window)
    dlg.setWindowTitle("Run command")
    dlg.setModal(True)
    dlg.resize(520, 380)

    v = QVBoxLayout(dlg)
    v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)
    inp = QLineEdit()
    inp.setPlaceholderText("Type to filter actions…")
    v.addWidget(inp)
    lst = QListWidget()
    v.addWidget(lst, 1)

    def populate(query: str):
        lst.clear()
        scored = []
        for prefix, a in actions:
            label = f"{prefix} ▸ {a.text().replace('&', '').replace('…', '...')}"
            sc = a.shortcut().toString()
            display = f"{label}  —  {sc}" if sc else label
            score = fuzzy_score(query, label)
            if score >= 0:
                scored.append((score, display, a))
        scored.sort(key=lambda x: -x[0])
        for _score, display, a in scored[:200]:
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, a)
            lst.addItem(item)
        if lst.count():
            lst.setCurrentRow(0)

    populate("")
    inp.textChanged.connect(populate)

    def trigger():
        item = lst.currentItem()
        if item is None:
            return
        action = item.data(Qt.ItemDataRole.UserRole)
        dlg.accept()
        action.trigger()

    inp.returnPressed.connect(trigger)
    lst.itemActivated.connect(lambda _: trigger())

    QShortcut(QKeySequence("Down"), inp, activated=lambda: lst.setCurrentRow(
        min(lst.count() - 1, lst.currentRow() + 1)))
    QShortcut(QKeySequence("Up"), inp, activated=lambda: lst.setCurrentRow(
        max(0, lst.currentRow() - 1)))
    inp.setFocus()
    return dlg


def _collect(menu, out: list, prefix: str = ""):
    for action in menu.actions():
        if action.isSeparator():
            continue
        sub = action.menu()
        if sub is not None:
            _collect(sub, out, prefix=f"{prefix} ▸ {action.text().replace('&', '')}")
        elif action.text():
            out.append((prefix, action))

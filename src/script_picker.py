"""Fuzzy "run a saved script" picker (F7).

Modeled on `command_palette.show_command_palette` — same modal shape,
same `fuzzy_score` ranker, but the items are the contents of
`agent_scripts.list_scripts()`. Up/Down navigates, Enter runs the
selected script via the existing Runner panel.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel,
)

from . import agent_scripts
from .command_palette import fuzzy_score


def show_script_picker(window):
    """Modal entry point used by the F7 shortcut."""
    dlg = build_script_picker(window)
    if dlg is not None:
        dlg.exec()


def build_script_picker(window):
    """Construct the dialog without `exec`'ing it. Returns the QDialog,
    or None when no scripts exist (status message already emitted)."""
    scripts = agent_scripts.list_scripts()
    if not scripts:
        window.statusBar().showMessage(
            f"No scripts saved yet. Use the chat panel to ask the agent "
            f"to create one — they live in {agent_scripts.SCRIPTS_DIR}.",
            6000,
        )
        return None

    dlg = QDialog(window)
    dlg.setWindowTitle("Run saved script")
    dlg.resize(560, 360)
    v = QVBoxLayout(dlg)
    v.setContentsMargins(8, 8, 8, 8)

    head = QLabel(
        f"<i>{len(scripts)} script(s) in "
        f"<code>{agent_scripts.SCRIPTS_DIR}</code></i>")
    v.addWidget(head)

    inp = QLineEdit()
    inp.setPlaceholderText("Filter by name or description…")
    v.addWidget(inp)

    lst = QListWidget()
    lst.setUniformItemSizes(True)
    v.addWidget(lst, 1)

    def _populate(query: str):
        lst.clear()
        scored: list[tuple[float, agent_scripts.Script]] = []
        for s in scripts:
            haystack = f"{s.name} {s.description}"
            if not query.strip():
                scored.append((1.0, s))
            else:
                score = fuzzy_score(query, haystack)
                if score > 0:
                    scored.append((score, s))
        scored.sort(key=lambda t: -t[0])
        for _, s in scored:
            label = f"{s.name}.{s.language[:2]}"
            if s.description:
                label += f"  —  {s.description}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s)
            lst.addItem(item)
        if lst.count():
            lst.setCurrentRow(0)

    _populate("")

    def _run_current():
        item = lst.currentItem()
        if item is None:
            return
        s: agent_scripts.Script = item.data(Qt.ItemDataRole.UserRole)
        try:
            window.run.panel.run_file(str(s.path))
            window.statusBar().showMessage(
                f"Running script '{s.name}' — output in Terminal panel.",
                4000)
        except Exception as e:
            window.statusBar().showMessage(
                f"Couldn't run '{s.name}': {e}", 5000)
        dlg.accept()

    inp.textChanged.connect(_populate)
    lst.itemActivated.connect(lambda *_: _run_current())

    # Keyboard nav: arrows in the input box should move the list.
    def _key(event):
        if event.key() == Qt.Key.Key_Down:
            lst.setCurrentRow(min(lst.count() - 1, lst.currentRow() + 1))
        elif event.key() == Qt.Key.Key_Up:
            lst.setCurrentRow(max(0, lst.currentRow() - 1))
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            _run_current()
        elif event.key() == Qt.Key.Key_Escape:
            dlg.reject()
        else:
            QLineEdit.keyPressEvent(inp, event)
    inp.keyPressEvent = _key

    inp.setFocus()
    return dlg

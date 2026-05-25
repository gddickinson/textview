"""New-from-template dialog (Ctrl+Alt+N).

Two-pane modal: a categorised list of `Template`s on the left, live
preview on the right. **Create as untitled** loads the body into the
viewer as a fresh, unsaved buffer; **Save to file…** prompts for a
path, writes the body, then opens that file (so detection + view mode
are right from the first click).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QPlainTextEdit, QFileDialog, QMessageBox, QSplitter, QWidget,
)

from .templates import list_templates, Template


_CATEGORY_HEADER = "::category::"  # sentinel for non-selectable list rows


def _make_list() -> QListWidget:
    lw = QListWidget()
    by_cat: dict[str, list[Template]] = {}
    for t in list_templates():
        by_cat.setdefault(t.category, []).append(t)
    for cat, items in by_cat.items():
        header = QListWidgetItem(f"— {cat} —")
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        header.setData(Qt.ItemDataRole.UserRole, _CATEGORY_HEADER)
        f = QFont(); f.setBold(True); header.setFont(f)
        lw.addItem(header)
        for t in items:
            it = QListWidgetItem(t.name)
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            lw.addItem(it)
    return lw


def show_new_from_template(window) -> None:
    """Modal launcher. Returns when the user chooses or cancels."""
    dlg = QDialog(window)
    dlg.setWindowTitle("New from template")
    dlg.resize(820, 540)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(10, 10, 10, 10)

    split = QSplitter(Qt.Orientation.Horizontal, dlg)

    left = QWidget(split)
    lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(6)
    lv.addWidget(QLabel("Templates:", left))
    lw = _make_list(); lv.addWidget(lw, 1)

    right = QWidget(split)
    rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(6)
    lbl_name = QLabel("Select a template to preview.", right)
    f = QFont(); f.setBold(True); lbl_name.setFont(f)
    lbl_desc = QLabel("", right); lbl_desc.setWordWrap(True)
    preview = QPlainTextEdit(right); preview.setReadOnly(True)
    preview.setFont(QFont("Menlo", 11))
    preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    rv.addWidget(lbl_name)
    rv.addWidget(lbl_desc)
    rv.addWidget(preview, 1)

    split.addWidget(left); split.addWidget(right)
    split.setStretchFactor(0, 1); split.setStretchFactor(1, 2)
    root.addWidget(split, 1)

    btn_row = QHBoxLayout(); btn_row.setSpacing(8)
    btn_create = QPushButton("Create as untitled")
    btn_save = QPushButton("Save to file…")
    btn_cancel = QPushButton("Cancel")
    btn_create.setEnabled(False); btn_save.setEnabled(False)
    btn_row.addStretch(1)
    btn_row.addWidget(btn_create); btn_row.addWidget(btn_save); btn_row.addWidget(btn_cancel)
    root.addLayout(btn_row)

    state: dict = {"template": None}

    def on_selection_changed():
        item = lw.currentItem()
        if item is None or item.data(Qt.ItemDataRole.UserRole) == _CATEGORY_HEADER:
            state["template"] = None
            btn_create.setEnabled(False); btn_save.setEnabled(False)
            lbl_name.setText("Select a template to preview."); lbl_desc.setText("")
            preview.setPlainText("")
            return
        from .templates import by_id
        t = by_id(item.data(Qt.ItemDataRole.UserRole))
        state["template"] = t
        if t is None: return
        lbl_name.setText(t.name)
        lbl_desc.setText(t.description or f"Default filename: {t.extension}")
        preview.setPlainText(t.body)
        btn_create.setEnabled(True); btn_save.setEnabled(True)

    lw.currentItemChanged.connect(lambda *_: on_selection_changed())

    def on_create():
        t = state["template"]
        if t is None: return
        _open_as_untitled(window, t)
        dlg.accept()

    def on_save():
        t = state["template"]
        if t is None: return
        if _save_then_open(window, t):
            dlg.accept()

    btn_create.clicked.connect(on_create)
    btn_save.clicked.connect(on_save)
    btn_cancel.clicked.connect(dlg.reject)
    # Double-click on the list is also "Create as untitled".
    lw.itemDoubleClicked.connect(lambda *_: on_create())

    dlg.exec()


def _open_as_untitled(window, t: Template) -> None:
    """Load the template body into the editor as an unsaved buffer.

    Uses the public `_show_welcome`-style path so the existing format
    detection and view-mode routing still apply.
    """
    if hasattr(window, "edit") and not window.edit.confirm_discard():
        return
    # Force the format so the renderer / Pygments pick it up even though
    # there's no path yet.
    window._current_path = None
    window._current_content = t.body
    window._current_format = t.format
    window._current_encoding = "utf-8"
    # PDF / rich / latex controllers may hold state for the prior file.
    if hasattr(window, "_pdf"): window._pdf.clear()
    if hasattr(window, "_rich"): window._rich.clear()
    if hasattr(window, "_latex"): window._latex.clear()
    try: window.viewer.video_view.teardown()
    except Exception: pass

    window.edit.reset()
    window.viewer.code.setPlainText(t.body)
    window.viewer.code.document().clearUndoRedoStacks()
    window.lbl_file.setText(f"Untitled ({t.extension})")
    window.lbl_format.setText(f"Format: {t.format}")
    window.lbl_encoding.setText("Encoding: utf-8")
    window.lbl_size.setText("")
    window.tab_bar.add_or_select(None, f"Untitled ({t.extension})")
    window._refresh_view(); window._update_title()
    # Drop straight into edit mode — the whole point is to type into it.
    window.edit.set_editing(True)
    window.statusBar().showMessage(f"New {t.name} (unsaved).", 4000)


def _save_then_open(window, t: Template) -> bool:
    """Prompt for a path, write the body, then open it normally."""
    default_dir = ""
    if window._current_path:
        default_dir = str(Path(window._current_path).parent)
    suggested = str(Path(default_dir) / t.extension) if default_dir else t.extension
    out, _ = QFileDialog.getSaveFileName(window, "Save new file as", suggested)
    if not out: return False
    try:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(t.body, encoding="utf-8")
    except OSError as e:
        QMessageBox.critical(window, "Could not create file", str(e))
        return False
    window.open_file(out, confirm=True)
    # Land in edit mode so the user can keep typing.
    try: window.edit.set_editing(True)
    except Exception: pass
    return True

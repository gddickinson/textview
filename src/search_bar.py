"""Inline find / replace bar.

Operates on any QTextEdit-derived widget (QPlainTextEdit, QTextBrowser).
Supports incremental highlighting of all matches, find next / previous with
wrap-around, case + whole-word toggles, and single / all replace when the
attached widget is editable.
"""
from PyQt6.QtCore import Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import (
    QShortcut, QKeySequence, QTextDocument, QTextCursor, QTextCharFormat,
    QColor,
)
from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QHBoxLayout, QCheckBox, QLabel,
    QTextEdit,
)


class SearchBar(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = None
        self._allow_replace = False
        self._build_ui()
        self.hide()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Find:"))
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search…")
        self.find_input.returnPressed.connect(self.find_next)
        self.find_input.textChanged.connect(self._on_query_changed)
        layout.addWidget(self.find_input, 2)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(28)
        self.btn_prev.setToolTip("Previous match (Shift+Enter)")
        self.btn_prev.clicked.connect(self.find_previous)
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(28)
        self.btn_next.setToolTip("Next match (Enter)")
        self.btn_next.clicked.connect(self.find_next)
        layout.addWidget(self.btn_next)

        self.cb_case = QCheckBox("Aa")
        self.cb_case.setToolTip("Match case")
        self.cb_case.toggled.connect(self._highlight_all)
        layout.addWidget(self.cb_case)

        self.cb_word = QCheckBox("W")
        self.cb_word.setToolTip("Whole words")
        self.cb_word.toggled.connect(self._highlight_all)
        layout.addWidget(self.cb_word)

        self.cb_regex = QCheckBox(".*")
        self.cb_regex.setToolTip("Treat the search box as a regular expression")
        self.cb_regex.toggled.connect(self._highlight_all)
        layout.addWidget(self.cb_regex)

        layout.addWidget(QLabel("Replace:"))
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("…")
        layout.addWidget(self.replace_input, 1)

        self.btn_replace = QPushButton("Replace")
        self.btn_replace.clicked.connect(self.replace_one)
        layout.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton("All")
        self.btn_replace_all.clicked.connect(self.replace_all)
        layout.addWidget(self.btn_replace_all)

        self.status = QLabel("")
        self.status.setMinimumWidth(90)
        layout.addWidget(self.status)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedWidth(28)
        self.btn_close.clicked.connect(self.hide_bar)
        layout.addWidget(self.btn_close)

        QShortcut(QKeySequence("Escape"), self, activated=self.hide_bar)
        QShortcut(QKeySequence("Shift+Return"), self, activated=self.find_previous)

        self.set_replace_enabled(False)

    # -- public API ----------------------------------------------------------

    def attach(self, target):
        """Set the text-edit widget the bar searches in."""
        # Clear highlights from prior target
        if self._target is not None and target is not self._target:
            try:
                self._target.setExtraSelections([])
            except Exception:
                pass
        self._target = target

    def set_replace_enabled(self, on):
        self._allow_replace = on
        self.replace_input.setEnabled(on)
        self.btn_replace.setEnabled(on)
        self.btn_replace_all.setEnabled(on)

    def show_and_focus(self):
        self.show()
        self.find_input.setFocus()
        self.find_input.selectAll()
        if self.find_input.text():
            self._highlight_all()

    def hide_bar(self):
        self.hide()
        if self._target is not None:
            try:
                self._target.setExtraSelections([])
            except Exception:
                pass
        self.closed.emit()

    # -- search logic --------------------------------------------------------

    def _flags(self, backward=False):
        flags = QTextDocument.FindFlag(0)
        if self.cb_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.cb_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _query(self):
        """Wrap the find input in QRegularExpression when regex is on."""
        text = self.find_input.text()
        if not self.cb_regex.isChecked():
            return text
        opts = QRegularExpression.PatternOption.NoPatternOption
        if not self.cb_case.isChecked():
            opts |= QRegularExpression.PatternOption.CaseInsensitiveOption
        rx = QRegularExpression(text, opts)
        return rx if rx.isValid() else text

    def find_next(self):
        if not self._target or not self.find_input.text():
            return
        q = self._query()
        if not self._target.find(q, self._flags()):
            cursor = self._target.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._target.setTextCursor(cursor)
            ok = self._target.find(q, self._flags())
            self.status.setText("Wrapped" if ok else "No matches")
        else:
            self._update_status()

    def find_previous(self):
        if not self._target or not self.find_input.text():
            return
        q = self._query()
        if not self._target.find(q, self._flags(backward=True)):
            cursor = self._target.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._target.setTextCursor(cursor)
            ok = self._target.find(q, self._flags(backward=True))
            self.status.setText("Wrapped" if ok else "No matches")
        else:
            self._update_status()

    def _on_query_changed(self):
        self._highlight_all()

    def _highlight_all(self):
        if self._target is None:
            return
        if not self.find_input.text():
            try:
                self._target.setExtraSelections([])
            except Exception:
                pass
            self.status.setText("")
            return
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#ffd54f"))
        fmt.setForeground(QColor("#000000"))
        flags = QTextDocument.FindFlag(0)
        if self.cb_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.cb_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        doc = self._target.document()
        q = self._query()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        selections = []
        count = 0
        while True:
            cursor = doc.find(q, cursor, flags)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            sel.cursor = cursor
            selections.append(sel)
            count += 1
            if count > 5000:
                break
        self._target.setExtraSelections(selections)
        self._match_count = count
        self.status.setText(f"{count} match{'es' if count != 1 else ''}")

    def _update_status(self):
        if hasattr(self, "_match_count"):
            self.status.setText(
                f"{self._match_count} match{'es' if self._match_count != 1 else ''}"
            )

    def _selection_matches_query(self, sel: str) -> bool:
        """Does a selection equal the find query under current flags?"""
        q = self.find_input.text()
        if self.cb_regex.isChecked():
            import re
            flags = 0 if self.cb_case.isChecked() else re.IGNORECASE
            try: return bool(re.fullmatch(q, sel, flags))
            except re.error: return False
        return sel == q if self.cb_case.isChecked() else sel.lower() == q.lower()

    def _expand_replacement(self, sel: str) -> str:
        """Expand `\\1`/`\\g<name>` etc. when regex mode is on; literal otherwise."""
        repl = self.replace_input.text()
        if not self.cb_regex.isChecked():
            return repl
        import re
        flags = 0 if self.cb_case.isChecked() else re.IGNORECASE
        try:
            m = re.fullmatch(self.find_input.text(), sel, flags)
            return m.expand(repl) if m else repl
        except re.error:
            return repl

    def replace_one(self):
        if not self._allow_replace or self._target is None: return
        if not self.find_input.text(): return
        cursor = self._target.textCursor()
        if cursor.hasSelection() and self._selection_matches_query(cursor.selectedText()):
            cursor.insertText(self._expand_replacement(cursor.selectedText()))
        self.find_next()
        self._highlight_all()

    def replace_all(self):
        if not self._allow_replace or self._target is None: return
        if not self.find_input.text(): return
        q = self._query()
        if self.cb_regex.isChecked() and isinstance(q, str):  # invalid pattern
            self.status.setText("Bad regex"); return
        doc = self._target.document()
        cursor = QTextCursor(doc); cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        count = 0
        try:
            while True:
                found = doc.find(q, cursor, self._flags())
                if found.isNull(): break
                found.insertText(self._expand_replacement(found.selectedText()))
                cursor = found; count += 1
                if count > 100000: break
        finally:
            cursor.endEditBlock()
        self.status.setText(f"Replaced {count}")
        self._highlight_all()

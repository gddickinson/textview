"""Stand-alone editor commands invoked by toolbar / menu actions.

Each function takes a `MainWindow` (or relevant widget) and operates on
the current code view. Kept separate from `app.py` so the actions stay
trivially testable and the main window stays under its line budget.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QInputDialog, QMessageBox


# Single-line comment markers per format. None means "no good default".
_COMMENT_PREFIX = {
    "python": "# ", "py": "# ",
    "javascript": "// ", "js": "// ", "ts": "// ", "tsx": "// ", "jsx": "// ",
    "c": "// ", "cpp": "// ", "java": "// ", "go": "// ", "rust": "// ",
    "rs": "// ", "swift": "// ", "kotlin": "// ", "kt": "// ", "scala": "// ",
    "css": "/* ",  # block-only — handled specially below
    "scss": "// ",
    "html": "<!-- ",
    "xml": "<!-- ",
    "sql": "-- ",
    "lua": "-- ",
    "ruby": "# ", "rb": "# ",
    "bash": "# ", "sh": "# ", "zsh": "# ",
    "yaml": "# ", "yml": "# ",
    "toml": "# ", "ini": "# ", "conf": "# ",
    "markdown": "<!-- ", "md": "<!-- ",
}


def goto_line(window):
    code = window.viewer.code
    block_count = code.document().blockCount()
    line, ok = QInputDialog.getInt(
        window, "Go to line", f"Line number (1-{block_count}):",
        min=1, max=block_count, value=code.textCursor().blockNumber() + 1,
    )
    if not ok:
        return
    cursor = code.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.Down,
                        QTextCursor.MoveMode.MoveAnchor, line - 1)
    code.setTextCursor(cursor)
    code.centerCursor()
    code.setFocus()


def update_counts(window):
    """Compute line/word/char counts for the active text view, push to status."""
    text = window._current_content or ""
    lines = max(1, text.count("\n") + (0 if text.endswith("\n") else 1)) if text else 0
    words = len(text.split())
    chars = len(text)
    window.lbl_size.setText(f"{lines} ln · {words} w · {chars} ch")


def convert_line_endings(window, target: str):
    """Normalize all line endings in the buffer to one of LF / CRLF / CR.

    `target` is one of "lf", "crlf", "cr". The window's status bar reports
    how many lines were affected.
    """
    code = window.viewer.code
    if code.isReadOnly():
        window.statusBar().showMessage("Enable edit mode (Ctrl+E) first.", 3000)
        return
    text = code.toPlainText()
    # Qt's QPlainTextEdit normalizes everything to '\n' on display, so the
    # buffer contents always use LF here. The conversion materializes when
    # we save back to disk — but we still expose this as a buffer-level
    # operation for cases where the user pastes mixed content.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if target == "crlf":
        new = normalized.replace("\n", "\r\n")
    elif target == "cr":
        new = normalized.replace("\n", "\r")
    else:
        new = normalized
    if new != text:
        cursor = code.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(new)
        cursor.endEditBlock()
    window.statusBar().showMessage(f"Line endings → {target.upper()}", 3000)


def convert_indentation(window, to_spaces: bool):
    """Convert tabs ↔ spaces using the current `tab_width` setting."""
    code = window.viewer.code
    if code.isReadOnly():
        window.statusBar().showMessage("Enable edit mode (Ctrl+E) first.", 3000)
        return
    width = max(1, window.settings_manager.display.tab_width)
    text = code.toPlainText()
    if to_spaces:
        new = text.expandtabs(width)
    else:
        # Replace runs of `width` spaces at the start of each line with a tab.
        out = []
        for line in text.split("\n"):
            stripped = line.lstrip(" ")
            indent = line[:len(line) - len(stripped)]
            tabs = "\t" * (len(indent) // width)
            rem = " " * (len(indent) % width)
            out.append(tabs + rem + stripped)
        new = "\n".join(out)
    if new != text:
        cursor = code.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(new)
        cursor.endEditBlock()


def toggle_line_comment(window):
    """Comment / uncomment selected lines (or current line) using the
    language's single-line marker, if known.
    """
    fmt = window._current_format
    prefix = _COMMENT_PREFIX.get(fmt)
    if not prefix:
        window.statusBar().showMessage(
            f"No comment marker known for '{fmt}'.", 3000
        )
        return
    code = window.viewer.code
    if code.isReadOnly():
        window.statusBar().showMessage(
            "Enable edit mode (Ctrl+E) to toggle comments.", 3000
        )
        return
    cursor = code.textCursor()
    cursor.beginEditBlock()
    try:
        if cursor.hasSelection():
            start_block = code.document().findBlock(cursor.selectionStart()).blockNumber()
            end_block = code.document().findBlock(cursor.selectionEnd()).blockNumber()
        else:
            start_block = end_block = cursor.blockNumber()
        # Decide whether to add or remove
        block = code.document().findBlockByNumber(start_block)
        all_commented = True
        b = block
        for _ in range(start_block, end_block + 1):
            text = b.text().lstrip()
            if text and not text.startswith(prefix.strip()):
                all_commented = False
                break
            b = b.next()
        # Apply: respect existing leading whitespace.
        b = block
        for _ in range(start_block, end_block + 1):
            line_cursor = QTextCursor(b)
            line_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            text = b.text()
            leading = len(text) - len(text.lstrip())
            indent, rest = text[:leading], text[leading:]
            if all_commented:
                # Strip the comment marker from the start of `rest` only,
                # preserving the original indent.
                if rest.startswith(prefix):
                    new_rest = rest[len(prefix):]
                elif rest.startswith(prefix.rstrip()):
                    new_rest = rest[len(prefix.rstrip()):]
                else:
                    new_rest = rest
                line_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                         QTextCursor.MoveMode.KeepAnchor)
                line_cursor.insertText(indent + new_rest)
            else:
                # Insert prefix after the indent so commented lines keep
                # their indentation alignment.
                line_cursor.movePosition(QTextCursor.MoveOperation.Right,
                                         QTextCursor.MoveMode.MoveAnchor, leading)
                line_cursor.insertText(prefix)
            b = b.next()
    finally:
        cursor.endEditBlock()

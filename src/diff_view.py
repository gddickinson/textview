"""Diff viewer.

Displays a unified diff in the existing code view, syntax-highlighted by
Pygments' built-in `diff` lexer (so `+` lines render green, `-` lines
render red, hunk headers are highlighted, etc.). Two entry points:

  * `compare_with_file(window)` — pick another file via QFileDialog and
    diff it against the currently-open file.
  * `compare_with_git_head(window)` — shell out to `git diff -- <path>`
    for the open file and show the result.

The diff is shown in `_current_format = "diff"` so save/export are still
available; we never touch the original on-disk files.
"""
import difflib
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox


def _read_lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError as e:
        raise RuntimeError(f"Could not read {path}: {e}")


def _show_diff(window, label: str, content: str):
    """Drop the diff into the code view and apply Pygments diff highlighting."""
    if not content.strip():
        window.statusBar().showMessage(f"No differences ({label}).", 4000)
        return
    from .renderers import apply_pygments
    from .themes import get_theme
    d = window.settings_manager.display
    theme = get_theme(d.theme)

    window._current_path = None
    window._current_content = content
    window._current_format = "diff"
    window._current_encoding = "utf-8"
    window.viewer.code.setPlainText(content)
    apply_pygments(window.viewer.code, content, "buffer.diff",
                   theme["pygments_style"], "diff")
    window.viewer.code.document().clearUndoRedoStacks()
    window.viewer.show_code()
    window.lbl_file.setText(label)
    window.lbl_format.setText("Format: diff")
    window.lbl_encoding.setText("")
    window.statusBar().showMessage(label, 4000)


def compare_with_file(window):
    if not window._current_path:
        QMessageBox.information(window, "Compare", "Open a file first.")
        return
    other, _ = QFileDialog.getOpenFileName(
        window, "Compare with…", str(Path(window._current_path).parent),
    )
    if not other:
        return
    a, b = window._current_path, other
    try:
        a_lines, b_lines = _read_lines(a), _read_lines(b)
    except RuntimeError as e:
        QMessageBox.critical(window, "Compare failed", str(e))
        return
    diff = "".join(difflib.unified_diff(
        a_lines, b_lines,
        fromfile=str(a), tofile=str(b),
        lineterm="",
    ))
    _show_diff(window, f"Diff: {Path(a).name} ↔ {Path(b).name}", diff)


def compare_with_git_head(window):
    if not window._current_path:
        QMessageBox.information(window, "Compare", "Open a file first.")
        return
    if shutil.which("git") is None:
        QMessageBox.warning(window, "Compare", "`git` not on PATH.")
        return
    p = Path(window._current_path).resolve()
    try:
        out = subprocess.run(
            ["git", "diff", "--no-color", "HEAD", "--", str(p)],
            capture_output=True, text=True, cwd=str(p.parent), timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        QMessageBox.critical(window, "Compare failed", str(e))
        return
    if out.returncode not in (0, 1):
        msg = (out.stderr or "").strip().splitlines()
        first = msg[0] if msg else f"git exit {out.returncode}"
        QMessageBox.warning(window, "Compare", f"git diff failed: {first}")
        return
    _show_diff(window, f"Diff: {p.name} ↔ HEAD", out.stdout)

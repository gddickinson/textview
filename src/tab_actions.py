"""Tab detach / move helpers and the tab right-click menu.

- `show_tab_context_menu(window, idx, global_pos)` — Close / Close other
  tabs / Detach to new window / Move to window → (other open windows).
- `detach_current_tab(window)` — Ctrl+Shift+T.
- `detach_to_new_window(source, path)` — spawn a fresh `MainWindow`, open
  `path` there, close its tab in `source`.
- `move_to_window(source, path, target)` — same, into an existing window.

The unsaved-changes prompt only fires when the tab being moved is the
source window's active (possibly dirty) buffer; inactive tabs always show
the on-disk file, so moving them is silent.
"""
from __future__ import annotations

from pathlib import Path


def _other_windows(window) -> list:
    from .app import MainWindow
    return [w for w in MainWindow._instances if w is not window and w.isVisible()]


def _release(source, path: str) -> bool:
    """Confirm discard if `path` is the active buffer; True if OK to move."""
    if path == source._current_path:
        if not source.edit.confirm_discard():
            return False
        source.edit.reset()
    return True


def move_to_window(source, path: str, target) -> bool:
    """Open `path` in `target` and close its tab in `source`."""
    if not path or target is source or not _release(source, path):
        return False
    target.open_file(path, confirm=True)
    source.tab_bar.close_tab(source.tab_bar.index_of(path))
    target.raise_(); target.activateWindow()
    return True


def detach_to_new_window(source, path: str):
    """Move `path` into a newly spawned window; returns it (or None)."""
    if not path or not _release(source, path):
        return None
    from .app import MainWindow
    target = MainWindow.spawn()
    target.open_file(path, confirm=False)
    source.tab_bar.close_tab(source.tab_bar.index_of(path))
    return target


def detach_current_tab(window):
    """Ctrl+Shift+T: detach the active tab (no-op on the welcome tab)."""
    if window._current_path:
        return detach_to_new_window(window, window._current_path)
    return None


def show_tab_context_menu(window, idx: int, global_pos) -> None:
    from PyQt6.QtWidgets import QMenu
    bar = window.tab_bar
    path = bar.bar.tabData(idx)
    menu = QMenu(window)
    menu.addAction("Close", lambda: bar.close_tab(idx))
    if bar.bar.count() > 1:
        def close_others():
            keep = bar.bar.tabData(idx)
            for i in reversed(range(bar.bar.count())):
                if bar.bar.tabData(i) != keep:
                    bar.close_tab(i)
        menu.addAction("Close other tabs", close_others)
    if path:
        menu.addSeparator()
        menu.addAction("Detach to new window",
                       lambda: detach_to_new_window(window, path))
        others = _other_windows(window)
        if others:
            sub = menu.addMenu("Move to window")
            for w in others:
                label = Path(w._current_path).name if w._current_path else "Welcome"
                sub.addAction(f"{w.windowTitle()} — {label}",
                              lambda w=w: move_to_window(window, path, w))
    menu.exec(global_pos)

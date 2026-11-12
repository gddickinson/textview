"""Tab right-click menu + detach / move (src/tab_actions.py).

Regression: `tab_actions.py` and `TabBar.tab_context_requested` were
referenced by `MainWindow.__init__` and `actions.build` but never
committed, so the window could not be constructed from a clean clone.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _window(qapp):
    os.chdir(ROOT)
    from PyQt6 import QtWebEngineWidgets  # noqa: F401
    from src.app import MainWindow
    w = MainWindow(); w.show(); qapp.processEvents()
    return w


def test_main_window_constructs_with_tab_context_signal(qapp):
    w = _window(qapp)
    assert hasattr(w.tab_bar, "tab_context_requested")
    assert w.action_detach_tab.shortcut().toString() == "Ctrl+Shift+T"
    w.close()


def test_detach_moves_tab_to_new_window(qapp):
    from src import tab_actions
    w = _window(qapp)
    a, b = "sample_files/example.py", "sample_files/example.md"
    w.open_file(a, confirm=False); w.open_file(b, confirm=False); qapp.processEvents()
    assert w.tab_bar.paths() == [a, b]
    new = tab_actions.detach_current_tab(w); qapp.processEvents()
    assert new is not None and new._current_path == b
    assert w.tab_bar.paths() == [a]
    assert w._current_path == a
    # and back again via move_to_window
    assert tab_actions.move_to_window(new, b, w); qapp.processEvents()
    assert b in w.tab_bar.paths() and b not in new.tab_bar.paths()
    new.close(); w.close()


def test_detach_on_welcome_is_noop(qapp):
    from src import tab_actions
    w = _window(qapp)
    w._show_welcome()
    assert tab_actions.detach_current_tab(w) is None
    w.close()

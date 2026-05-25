"""Notebook + Python REPL action handlers, factored out of MainWindow.

These were inline in `app.py` until the file outgrew the 500-line cap.
Each function takes the `MainWindow` as `window`; behaviour is
unchanged.
"""
from __future__ import annotations

import sys


def open_python_repl(window):
    from .python_envs import open_repl
    open_repl(window)


def pick_python_interpreter(window):
    from .python_envs import pick_interpreter
    pick_interpreter(window)


def open_jupyter_console(window):
    window.jupyter_dock.show()
    if not window.jupyter_dock.is_running():
        interpreter = (window.settings_manager.display.python_interpreter
                       or sys.executable)
        window.jupyter_dock.start_with_interpreter(interpreter)


def notebook_start_kernel(window):
    interpreter = (window.settings_manager.display.python_interpreter
                   or sys.executable)
    window.viewer.notebook_view.start_kernel(interpreter)


def notebook_run_all(window):
    window.viewer.notebook_view.run_all()


def _nb_op(window, fn: str, *args):
    nv = window.viewer.notebook_view
    cur = nv.current_cell()
    if fn == "add":
        nv.add_cell(cur.index if cur else -1, *args)
    elif cur:
        getattr(nv, fn)(cur.index, *args)


def notebook_add_cell(window, kind: str):
    _nb_op(window, "add", kind)


def notebook_delete_current(window):
    _nb_op(window, "delete_cell")


def notebook_change_type(window, k: str):
    _nb_op(window, "change_cell_type", k)


def notebook_move(window, d: int):
    _nb_op(window, "move_cell", d)

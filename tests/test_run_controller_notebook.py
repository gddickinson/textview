"""F5 / Run on a .ipynb routes to NotebookView.run_all, not the legacy
`jupyter execute` shell-out (which crashes on the anaconda+sqlite ABI bug)."""
import os
from pathlib import Path
import pytest


def test_run_current_dispatches_to_notebook_view(qapp, tmp_path, monkeypatch):
    """When `_current_format == 'notebook'`, run_current should call
    `notebook_view.run_all()` and NOT spawn a subprocess via `Runner`."""
    os.chdir(Path(__file__).resolve().parent.parent)
    from PyQt6 import QtWebEngineWidgets  # noqa: F401
    from src.app import MainWindow

    w = MainWindow(); w.show(); qapp.processEvents()
    w.open_file("sample_files/example.ipynb"); qapp.processEvents()
    assert w._current_format == "notebook"

    run_all_called = []
    monkeypatch.setattr(w.viewer.notebook_view, "run_all",
                        lambda: run_all_called.append(True))
    runner_called = []
    monkeypatch.setattr(w.run.panel.runner, "run_file",
                        lambda *a, **k: runner_called.append(True))

    w.run.run_current()
    assert run_all_called == [True]
    assert runner_called == []   # legacy `jupyter execute` path skipped

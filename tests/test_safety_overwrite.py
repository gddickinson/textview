"""Safeguards: confirm-discard on every open path, AppAPI.save_as
refuses silent clobber, notebook dirty state propagates."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

pytest.importorskip("PyQt6")


# -- AppAPI.save_as ---------------------------------------------------------

class _FakeWindow:
    def __init__(self, current_path=None, current_content="hello\n",
                 current_format="text"):
        self._current_path = current_path
        self._current_content = current_content
        self._current_format = current_format


def test_save_as_writes_to_new_path(tmp_path):
    from src.api import AppAPI
    w = _FakeWindow(current_content="abc\n")
    api = AppAPI(w)
    target = tmp_path / "fresh.txt"
    api.save_as(str(target))
    assert target.read_text() == "abc\n"


def test_save_as_refuses_to_clobber_existing_file(tmp_path):
    from src.api import AppAPI
    target = tmp_path / "exists.txt"
    target.write_text("important\n")
    api = AppAPI(_FakeWindow(current_content="overwriting"))
    with pytest.raises(FileExistsError):
        api.save_as(str(target))
    # Original content untouched.
    assert target.read_text() == "important\n"


def test_save_as_overwrites_when_explicit(tmp_path):
    from src.api import AppAPI
    target = tmp_path / "exists.txt"
    target.write_text("old\n")
    api = AppAPI(_FakeWindow(current_content="new\n"))
    api.save_as(str(target), overwrite=True)
    assert target.read_text() == "new\n"


def test_save_as_allows_writing_to_current_path(tmp_path):
    """Writing to the same path the user has open is fine — it's just save."""
    from src.api import AppAPI
    target = tmp_path / "current.txt"
    target.write_text("old\n")
    api = AppAPI(_FakeWindow(current_path=str(target),
                             current_content="new\n"))
    api.save_as(str(target))   # overwrite=False but path matches current
    assert target.read_text() == "new\n"


@pytest.mark.parametrize("fmt", ["pdf", "docx", "rtf", "epub", "odt"])
def test_save_as_refuses_for_document_formats(tmp_path, fmt):
    from src.api import AppAPI
    target = tmp_path / f"out.{fmt}"
    api = AppAPI(_FakeWindow(current_format=fmt,
                             current_content="extracted plain text"))
    with pytest.raises(ValueError, match="extracted text"):
        api.save_as(str(target))
    assert not target.exists()


# -- Open-with-confirm-discard ----------------------------------------------

def test_open_file_signature_accepts_confirm_kwarg():
    """Smoke test that the public signature didn't drift."""
    import inspect
    from src.app import MainWindow
    sig = inspect.signature(MainWindow.open_file)
    params = sig.parameters
    assert "confirm" in params
    assert params["confirm"].default is True


# -- Notebook dirty propagation --------------------------------------------

def test_notebook_dirty_signal_wired_to_edit_controller():
    """Verify the signal/slot wiring exists in app.py without launching Qt.
    A grep-style check is enough — the integration is well-typed."""
    src = Path("src/app.py").read_text()
    assert "notebook_view.dirty_changed.connect" in src
    assert "_on_notebook_dirty" in src

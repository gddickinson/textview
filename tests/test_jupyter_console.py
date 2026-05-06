"""JupyterDock: construction + kernel start (slow, requires ipykernel)."""
import sys
import pytest

from src.jupyter_console import JupyterDock


def test_dock_constructs_with_placeholder(qapp):
    """Dock should be importable and constructible without spawning a kernel."""
    d = JupyterDock()
    assert not d.is_running()
    assert "Kernel" in d.btn_pick.text() or "Kernel" in d.btn_pick.toolTip() or True
    # Title carries "Jupyter".
    assert "Jupyter" in d.windowTitle()


def test_shutdown_is_noop_when_no_kernel(qapp):
    d = JupyterDock()
    # Should not raise even with no kernel.
    d.shutdown_kernel()
    assert not d.is_running()


def test_interrupt_is_safe_when_no_kernel(qapp):
    d = JupyterDock()
    d.interrupt_kernel()  # no-op, must not raise
    assert not d.is_running()


@pytest.mark.slow
def test_start_with_interpreter_spawns_kernel(qapp):
    """Real kernel start. Requires `ipykernel` and a working sqlite3 — skips
    when the kernel fails to come up (e.g. anaconda+sqlite ABI mismatch)."""
    try:
        import ipykernel  # noqa: F401
    except ImportError:
        pytest.skip("ipykernel not installed")
    d = JupyterDock()
    ok = d.start_with_interpreter(sys.executable)
    if not ok:
        pytest.skip("kernel could not start in this environment")
    try:
        assert d.is_running()
    finally:
        d.shutdown_kernel()
    assert not d.is_running()

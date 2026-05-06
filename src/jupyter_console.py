"""Embedded Jupyter qtconsole — IPython REPL inside a `QDockWidget`.

Wraps `qtconsole.rich_jupyter_widget.RichJupyterWidget` and a kernel
managed by `jupyter_client.manager.QtKernelManager`. The kernel is one
process per dock; restart/interrupt/pick-interpreter live on the dock's
toolbar.

The dock is lazily wired — we don't construct the widget until the user
opens it (qtconsole pulls in matplotlib backends, etc., which takes a
moment). On macOS / Windows / Linux. Falls back to a status-bar message
if `qtconsole` isn't installed.

Picking an interpreter starts a kernel using that python's `ipykernel`
module via `python -m ipykernel_launcher` — so any conda env the user
selects will run there, as long as it has `ipykernel` installed.
"""
from __future__ import annotations
import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QLabel,
    QMessageBox, QInputDialog,
)


def _ensure_qt_api():
    """qtconsole picks its Qt binding from the QT_API env var. PyQt6 must be
    set explicitly or qtconsole tries every binding in turn."""
    os.environ.setdefault("QT_API", "pyqt6")


class JupyterDock(QDockWidget):
    """Right-side dock hosting a `RichJupyterWidget` + a thin toolbar."""

    kernel_started = pyqtSignal(str)   # interpreter path or kernel name
    kernel_died = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Jupyter", parent)
        self.setObjectName("jupyter_dock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        body = QWidget(); v = QVBoxLayout(body); v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout(); bar.setContentsMargins(4, 2, 4, 2)
        self.btn_pick = QToolButton(); self.btn_pick.setText("Kernel…")
        self.btn_restart = QToolButton(); self.btn_restart.setText("⟳ Restart")
        self.btn_interrupt = QToolButton(); self.btn_interrupt.setText("⏹ Interrupt")
        self.lbl_status = QLabel("idle")
        self.lbl_status.setStyleSheet("color: #888;")
        bar.addWidget(self.btn_pick); bar.addWidget(self.btn_restart)
        bar.addWidget(self.btn_interrupt); bar.addStretch(1)
        bar.addWidget(self.lbl_status)
        v.addLayout(bar)
        self._jupyter_widget: QWidget | None = None
        self._km = None  # KernelManager
        self._kc = None  # KernelClient
        self._placeholder = QLabel(
            "Jupyter qtconsole — click 'Kernel…' to start.\n"
            "(Requires `qtconsole`, `jupyter_client`, and `ipykernel`.)")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; padding: 24px;")
        v.addWidget(self._placeholder, 1)
        self.setWidget(body)
        self.btn_pick.clicked.connect(self._on_pick)
        self.btn_restart.clicked.connect(self.restart_kernel)
        self.btn_interrupt.clicked.connect(self.interrupt_kernel)

    # -- lifecycle -----------------------------------------------------------

    def start_with_interpreter(self, interpreter: str) -> bool:
        """Spawn a kernel via `<interpreter> -m ipykernel_launcher`."""
        try:
            _ensure_qt_api()
            from qtconsole.rich_jupyter_widget import RichJupyterWidget
            from qtconsole.manager import QtKernelManager
        except ImportError as e:
            self._fail(f"qtconsole not available: {e}"); return False

        self.shutdown_kernel()
        km = QtKernelManager()
        km.kernel_cmd = [interpreter, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        try:
            km.start_kernel()
        except Exception as e:
            self._fail(f"kernel failed to start: {e}"); return False
        # `QtKernelClient` is async — it has no `wait_for_ready`. The
        # `RichJupyterWidget` handles readiness internally via signals;
        # we just connect channels and let it render.
        kc = km.client(); kc.start_channels()
        # Sanity check: the kernel subprocess is still alive after
        # start_kernel returns (catches IPython import crashes like the
        # anaconda+sqlite3 ABI mismatch — the QProcess starts then exits).
        if hasattr(km, "is_alive") and not km.is_alive():
            try: km.shutdown_kernel(now=True)
            except Exception: pass
            self._fail("kernel exited immediately (check Python env)"); return False

        widget = RichJupyterWidget()
        widget.kernel_manager = km; widget.kernel_client = kc
        # Swap placeholder for the live widget.
        self._placeholder.hide()
        self.widget().layout().addWidget(widget, 1)
        self._jupyter_widget = widget
        self._km = km; self._kc = kc
        self.lbl_status.setText(f"running · {os.path.basename(interpreter)}")
        self.lbl_status.setStyleSheet("color: #4caf50;")
        self.kernel_started.emit(interpreter)
        return True

    def restart_kernel(self):
        if self._km is None:
            self.lbl_status.setText("no kernel"); return
        try: self._km.restart_kernel(now=True)
        except Exception as e:
            self._fail(f"restart failed: {e}"); return
        self.lbl_status.setText("restarted"); self.lbl_status.setStyleSheet("color: #4caf50;")

    def interrupt_kernel(self):
        if self._km is None: return
        try: self._km.interrupt_kernel()
        except Exception as e: self._fail(f"interrupt failed: {e}")

    def shutdown_kernel(self):
        if self._kc is not None:
            try: self._kc.stop_channels()
            except Exception: pass
            self._kc = None
        if self._km is not None:
            try: self._km.shutdown_kernel(now=True)
            except Exception: pass
            self._km = None
        if self._jupyter_widget is not None:
            self._jupyter_widget.setParent(None)
            self._jupyter_widget = None
        self._placeholder.show()
        self.lbl_status.setText("idle"); self.lbl_status.setStyleSheet("color: #888;")

    # -- helpers -------------------------------------------------------------

    def is_running(self) -> bool:
        if self._km is None: return False
        # jupyter_client 7.x exposed has_kernel() as a method; 8.x as a bool
        # property. Be tolerant of both.
        has = getattr(self._km, "has_kernel", False)
        return has() if callable(has) else bool(has)

    def _fail(self, msg: str):
        self.lbl_status.setText(msg[:80])
        self.lbl_status.setStyleSheet("color: #e53935;")

    def _on_pick(self):
        from .python_envs import discover_all
        envs = discover_all()
        if not envs:
            QMessageBox.warning(self, "No interpreters",
                "No Python interpreters found on PATH or via conda/pyenv.")
            return
        labels = [f"{e.source}: {e.name}  —  {e.path}" for e in envs]
        choice, ok = QInputDialog.getItem(self, "Choose kernel interpreter",
            "Select the Python that will host the kernel:",
            labels, 0, False)
        if not ok: return
        env = envs[labels.index(choice)]
        self.start_with_interpreter(env.path)

    def closeEvent(self, ev):
        self.shutdown_kernel(); super().closeEvent(ev)

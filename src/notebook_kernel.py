"""Single shared Jupyter kernel for the notebook view.

Wraps `jupyter_client.KernelManager` and parses iopub messages into the
five output kinds nbformat cares about: stream, execute_result,
display_data, error, status. Doesn't touch any UI; the notebook view
listens via signals.
"""
from __future__ import annotations
import queue, threading
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


def _short_error(exc: BaseException) -> str:
    """One-line summary of an exception, walking the chain to surface root
    causes. Distinct lines from the chain join with ' ⇐ '."""
    parts = []
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur).strip().splitlines()[0] if str(cur).strip() else type(cur).__name__
        parts.append(msg)
        cur = cur.__cause__ or cur.__context__
        if len(parts) >= 3: break
    return " ⇐ ".join(parts)


class KernelHost(QObject):
    """Owns one kernel + its client. Polls iopub on a Qt timer."""

    started = pyqtSignal()
    output = pyqtSignal(str, dict)        # (msg_id, msg) where msg is the LSP-shaped iopub payload
    execute_complete = pyqtSignal(str)    # msg_id when status=idle after execute_input
    busy = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._km = None
        self._kc = None
        self._timer = QTimer(self); self._timer.setInterval(40)
        self._timer.timeout.connect(self._drain_iopub)
        self._active_msg: str | None = None
        self.last_error: str = ""

    def is_running(self) -> bool:
        return self._km is not None and self._kc is not None

    def start(self, interpreter: str = "python3") -> bool:
        self.last_error = ""
        try:
            from jupyter_client.manager import KernelManager
        except ImportError as e:
            self.last_error = f"jupyter_client not available: {e}"; return False
        self.shutdown()
        km = KernelManager()
        km.kernel_cmd = [interpreter, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        try:
            km.start_kernel()
        except Exception as e:
            self.last_error = _short_error(e); return False
        # If the kernel subprocess crashed during init (e.g. anaconda+sqlite3
        # ABI mismatch — IPython fails to import), `is_alive()` flips to False
        # before we can call `wait_for_ready`. Capture that case explicitly.
        if hasattr(km, "is_alive") and not km.is_alive():
            self.last_error = ("kernel process exited immediately. "
                "Check the Python env runs `python -c 'import IPython'` cleanly.")
            try: km.shutdown_kernel(now=True)
            except Exception: pass
            return False
        kc = km.client(); kc.start_channels()
        try: kc.wait_for_ready(timeout=10)
        except Exception as e:
            self.last_error = f"kernel never became ready: {_short_error(e)}"
            try: km.shutdown_kernel(now=True)
            except Exception: pass
            return False
        self._km = km; self._kc = kc
        self._timer.start()
        self.started.emit()
        return True

    def execute(self, code: str) -> str:
        """Send `code` for execution. Returns the request msg_id; iopub
        replies tagged with that parent will route through `output`."""
        if not self.is_running(): return ""
        msg_id = self._kc.execute(code, store_history=True)
        self._active_msg = msg_id
        return msg_id

    def interrupt(self):
        if self._km is not None:
            try: self._km.interrupt_kernel()
            except Exception: pass

    def restart(self):
        if self._km is not None:
            try: self._km.restart_kernel(now=True)
            except Exception: pass

    def shutdown(self):
        self._timer.stop()
        if self._kc is not None:
            try: self._kc.stop_channels()
            except Exception: pass
            self._kc = None
        if self._km is not None:
            try: self._km.shutdown_kernel(now=True)
            except Exception: pass
            self._km = None
        self._active_msg = None

    # -- iopub pump ----------------------------------------------------------

    def _drain_iopub(self):
        if self._kc is None: return
        # Pull all available messages this tick. get_iopub_msg(timeout=0)
        # raises queue.Empty when there's nothing pending.
        for _ in range(64):
            try: msg = self._kc.get_iopub_msg(timeout=0)
            except queue.Empty: return
            except Exception: return
            self._handle_iopub(msg)

    def _handle_iopub(self, msg: dict):
        parent_id = (msg.get("parent_header") or {}).get("msg_id", "")
        msg_type = msg.get("msg_type") or msg.get("header", {}).get("msg_type")
        if msg_type == "status":
            state = (msg.get("content") or {}).get("execution_state", "")
            self.busy.emit(state == "busy")
            if state == "idle" and parent_id == self._active_msg:
                self.execute_complete.emit(parent_id)
                self._active_msg = None
            return
        if msg_type in ("stream", "execute_result", "display_data", "error"):
            self.output.emit(parent_id, {
                "msg_type": msg_type,
                "content": msg.get("content") or {},
            })

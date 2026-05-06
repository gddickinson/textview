"""External control channel — drive every GUI operation from another
process. Listens on TCP localhost; speaks line-delimited JSON.

Each request is one JSON object per line:
    {"op": "open_file", "args": {"path": "/tmp/x.md"}}
Each reply is one JSON object per line:
    {"ok": true,  "result": {...}}
    {"ok": false, "error": "...",  "trace": "..."}

The server runs in the Qt event loop, so command dispatch happens on the
main thread — calling `MainWindow` methods is safe. Loopback only by
default; not exposed to the network. Disabled unless a port is given.

Built-in operations:
    state       — current path / format / mode / editing / modified
    open_file   — load a file
    save / save_as — through `EditController`
    set_text    — overwrite the code buffer (forces edit mode)
    get_text    — return current_content + buffer text + a snippet
    enter_edit / exit_edit — toggle edit mode
    trigger_action — fire any `MainWindow.action_*` by name
    list_actions   — every action name
    setting / set_setting — read / write `DisplaySettings` fields
    refresh        — call `_refresh_view`
    screenshot     — write a PNG of the main window to disk
    eval           — run an expression (or block) in `{"w": MainWindow}` scope
"""
from __future__ import annotations
import json, traceback
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QTcpServer, QHostAddress


class ControlServer(QObject):
    started = pyqtSignal(int)        # port
    request_received = pyqtSignal(str, dict)
    error = pyqtSignal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._connections: list = []

    def listen(self, port: int = 0) -> int:
        """Start listening. Returns the actual port (chosen by OS if 0).
        Returns -1 on failure."""
        ok = self._server.listen(QHostAddress.SpecialAddress.LocalHost, port)
        if not ok: return -1
        actual = self._server.serverPort()
        self.started.emit(actual)
        return actual

    def stop(self):
        for sock in list(self._connections):
            try: sock.disconnectFromHost()
            except Exception: pass
        self._server.close()

    def is_listening(self) -> bool:
        return self._server.isListening()

    # -- network -------------------------------------------------------------

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._connections.append(sock)
            sock.readyRead.connect(lambda s=sock: self._on_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnect(s))

    def _on_disconnect(self, sock):
        if sock in self._connections: self._connections.remove(sock)
        sock.deleteLater()

    def _on_read(self, sock):
        while sock.canReadLine():
            line = bytes(sock.readLine()).decode("utf-8", errors="replace").strip()
            if not line: continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as e:
                self._send(sock, {"ok": False, "error": f"bad JSON: {e}"}); continue
            self._dispatch(req, sock)

    def _dispatch(self, req: dict, sock):
        op = req.get("op", "")
        args = req.get("args") or {}
        if not isinstance(args, dict):
            self._send(sock, {"ok": False, "error": "args must be an object"}); return
        self.request_received.emit(op, args)
        handler = getattr(self, f"_op_{op}", None)
        if handler is None:
            self._send(sock, {"ok": False, "error": f"unknown op: {op!r}"}); return
        try:
            result = handler(**args)
            self._send(sock, {"ok": True, "result": result})
        except TypeError as e:
            self._send(sock, {"ok": False, "error": f"bad args for {op}: {e}"})
        except Exception as e:
            self._send(sock, {"ok": False, "error": str(e),
                              "trace": traceback.format_exc()})

    def _send(self, sock, payload: dict):
        sock.write((json.dumps(payload, default=str) + "\n").encode("utf-8"))
        sock.flush()

    # -- ops -----------------------------------------------------------------

    def _op_state(self):
        w = self.window; v = w.viewer
        return {
            "path": w._current_path,
            "format": w._current_format,
            "mode": v.mode(),
            "editing": w.edit.editing,
            "modified": w.edit.modified,
            "buffer_len": len(v.code.toPlainText()),
            "current_content_len": len(w._current_content or ""),
            "title": w.windowTitle(),
        }

    def _op_open_file(self, path: str):
        self.window.open_file(path); return self._op_state()

    def _op_save(self):
        ok = self.window.edit.save()
        return {"saved": ok, **self._op_state()}

    def _op_save_as(self, path: str):
        # Set the path and save through the controller's save() rather than
        # save_as() (which always shows a dialog).
        from pathlib import Path as _P
        self.window._current_path = str(path)
        ok = self.window.edit.save()
        return {"saved": ok, **self._op_state()}

    def _op_get_text(self):
        cv = self.window.viewer.code
        return {"buffer": cv.toPlainText(),
                "current_content": self.window._current_content,
                "buffer_head": cv.toPlainText()[:500]}

    def _op_set_text(self, text: str, enter_edit: bool = True):
        if enter_edit and not self.window.edit.editing:
            self.window.edit.set_editing(True)
        self.window.viewer.code.setPlainText(text)
        return self._op_state()

    def _op_enter_edit(self):
        # Skip if the format isn't editable — otherwise EditController shows
        # a blocking modal dialog and freezes the control server thread.
        if not self.window.edit.can_edit(self.window._current_format):
            return {**self._op_state(),
                    "refused": f"{self.window._current_format!r} is read-only"}
        if not self.window.edit.editing: self.window.edit.set_editing(True)
        return self._op_state()

    def _op_exit_edit(self):
        if self.window.edit.editing: self.window.edit.set_editing(False)
        return self._op_state()

    def _op_trigger_action(self, name: str):
        a = getattr(self.window, name, None)
        if a is None or not hasattr(a, "trigger"):
            raise ValueError(f"no action {name!r} on MainWindow")
        a.trigger()
        return self._op_state()

    def _op_list_actions(self):
        out = []
        for name in dir(self.window):
            if not name.startswith("action_"): continue
            a = getattr(self.window, name)
            if hasattr(a, "trigger"):
                out.append({"name": name,
                            "text": a.text().replace("&", ""),
                            "shortcut": a.shortcut().toString()})
        return out

    def _op_setting(self, key: str):
        return {key: getattr(self.window.settings_manager.display, key, None)}

    def _op_set_setting(self, key: str, value):
        self.window.settings_manager.update(key, value)
        return self._op_setting(key=key)

    def _op_refresh(self):
        self.window._refresh_view(); return self._op_state()

    def _op_screenshot(self, path: str):
        pm = self.window.grab()
        ok = pm.save(str(path))
        return {"saved": ok, "path": str(path),
                "size": [pm.width(), pm.height()]}

    def _op_eval(self, code: str):
        """Run `code` with `w` bound to MainWindow. Try eval first; fall
        back to exec for statements."""
        ns = {"w": self.window}
        try:
            result = eval(code, ns)
            return {"value": repr(result)}
        except SyntaxError:
            exec(code, ns)
            return {"value": "(exec)"}

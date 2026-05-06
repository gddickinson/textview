"""LSP client scaffold — JSON-RPC over stdio to a language server.

This module is the thin protocol layer: lifecycle (initialize / initialized
/ shutdown / exit), text-sync notifications (didOpen / didChange / didClose),
and a generic `send_request` for things like `textDocument/hover`. Higher-
level UI (diagnostics gutter dots, hover tooltips) lives elsewhere — this
file only speaks bytes on the wire.

Target: pyright (`pyright-langserver --stdio`). Anything that follows LSP
3.16+ should plug in by passing a different `command`.

Design:
    - `LSPClient(command, parent)` wraps a `QProcess`.
    - `start(root_uri)` spawns it, sends `initialize`, then `initialized`.
    - `did_open / did_change / did_close` are fire-and-forget.
    - `send_request(method, params)` returns an `int` request id; the
      future-style result is delivered via `response_received(id, result, err)`.
    - `notification_received(method, params)` fires on every server-sent
      notification (e.g., `textDocument/publishDiagnostics`).
"""
from __future__ import annotations
import json
from typing import Any
from PyQt6.QtCore import QObject, QProcess, pyqtSignal


def to_uri(path: str) -> str:
    """Path → file URI (no scheme parsing — assumes absolute path)."""
    p = str(path)
    if p.startswith("file://"): return p
    if p.startswith("/"):       return "file://" + p
    return "file:///" + p.replace("\\", "/")


class LSPClient(QObject):
    """Protocol-only LSP client. Owns the subprocess and the parser."""

    started_ok = pyqtSignal()
    response_received = pyqtSignal(int, object, object)   # id, result, error
    notification_received = pyqtSignal(str, object)       # method, params
    log = pyqtSignal(str, str)                            # level, message
    exited = pyqtSignal(int)                              # exit code

    def __init__(self, command: list[str], parent=None):
        super().__init__(parent)
        self.command = list(command)
        self.proc: QProcess | None = None
        self._buf = bytearray()
        self._next_id = 1
        self._pending: dict[int, str] = {}   # id → method (for trace/log)
        self._initialized = False
        self._capabilities: dict | None = None

    # -- lifecycle -----------------------------------------------------------

    def start(self, root_uri: str | None = None,
              workspace_folders: list[dict] | None = None,
              client_capabilities: dict | None = None) -> bool:
        if self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning:
            return False
        if not self.command:
            return False
        proc = QProcess(self)
        proc.setProgram(self.command[0])
        proc.setArguments(self.command[1:])
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(lambda code, _s: self.exited.emit(int(code)))
        self.proc = proc
        proc.start()
        if not proc.waitForStarted(3000):
            self.log.emit("error", f"failed to start {self.command!r}")
            self.proc = None
            return False
        # Send initialize (we don't block — the response arrives via _dispatch).
        params = {
            "processId": None,
            "rootUri": root_uri,
            "workspaceFolders": workspace_folders,
            "capabilities": client_capabilities or _default_client_capabilities(),
            "clientInfo": {"name": "TextView", "version": "0.1"},
        }
        self.send_request("initialize", params)
        return True

    def shutdown(self):
        if self.proc is None: return
        if self._initialized:
            try: self.send_request("shutdown", None)
            except Exception: pass
            self._send_message({"jsonrpc": "2.0", "method": "exit"})
        self.proc.waitForFinished(2000)
        try: self.proc.kill()
        except Exception: pass
        self.proc = None
        self._initialized = False

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    # -- text sync -----------------------------------------------------------

    def did_open(self, uri: str, language_id: str, version: int, text: str):
        self._send_message({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": uri, "languageId": language_id,
                "version": int(version), "text": text}},
        })

    def did_change(self, uri: str, version: int, text: str):
        # Full-document sync — simpler than incremental, fine for editor-sized buffers.
        self._send_message({
            "jsonrpc": "2.0", "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": uri, "version": int(version)},
                "contentChanges": [{"text": text}]},
        })

    def did_close(self, uri: str):
        self._send_message({
            "jsonrpc": "2.0", "method": "textDocument/didClose",
            "params": {"textDocument": {"uri": uri}},
        })

    # -- generic request -----------------------------------------------------

    def send_request(self, method: str, params: Any) -> int:
        rid = self._next_id; self._next_id += 1
        self._pending[rid] = method
        self._send_message({
            "jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return rid

    def hover(self, uri: str, line: int, character: int) -> int:
        return self.send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": int(line), "character": int(character)}})

    def definition(self, uri: str, line: int, character: int) -> int:
        return self.send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": int(line), "character": int(character)}})

    def references(self, uri: str, line: int, character: int,
                   include_declaration: bool = True) -> int:
        return self.send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": int(line), "character": int(character)},
            "context": {"includeDeclaration": bool(include_declaration)}})

    # -- wire ----------------------------------------------------------------

    def _send_message(self, msg: dict):
        if self.proc is None: return
        body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.proc.write(header + body)

    def _on_stdout(self):
        if self.proc is None: return
        chunk = bytes(self.proc.readAllStandardOutput())
        if not chunk: return
        self._buf.extend(chunk)
        for msg in self._drain_messages():
            self._dispatch(msg)

    def _on_stderr(self):
        if self.proc is None: return
        chunk = bytes(self.proc.readAllStandardError())
        if chunk:
            self.log.emit("stderr", chunk.decode("utf-8", "replace").rstrip())

    def _drain_messages(self):
        """Pull as many complete `Content-Length`-framed messages as possible
        out of `_buf`, leaving any partial tail behind."""
        out = []
        while True:
            sep = self._buf.find(b"\r\n\r\n")
            if sep < 0: break
            header_bytes = bytes(self._buf[:sep])
            length = _parse_content_length(header_bytes)
            if length is None:   # malformed header; discard up to separator
                del self._buf[:sep + 4]; continue
            total = sep + 4 + length
            if len(self._buf) < total: break
            body = bytes(self._buf[sep + 4:total])
            del self._buf[:total]
            try:
                out.append(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError as e:
                self.log.emit("error", f"bad JSON from server: {e}")
        return out

    def _dispatch(self, msg: dict):
        if "id" in msg and ("result" in msg or "error" in msg):
            rid = msg["id"]
            if isinstance(rid, int):
                method = self._pending.pop(rid, "")
                if method == "initialize":
                    res = msg.get("result") or {}
                    self._capabilities = res.get("capabilities", {})
                    self._send_message({"jsonrpc": "2.0", "method": "initialized", "params": {}})
                    self._initialized = True
                    self.started_ok.emit()
                self.response_received.emit(int(rid), msg.get("result"), msg.get("error"))
            return
        if "method" in msg:
            method = msg["method"]
            params = msg.get("params")
            if "id" in msg:
                # Server→client request — minimal: reply with null result so the
                # server doesn't stall. Real clients would handle workspace/*.
                self._send_message({"jsonrpc": "2.0", "id": msg["id"], "result": None})
            self.notification_received.emit(method, params)


def _parse_content_length(header: bytes) -> int | None:
    for line in header.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try: return int(line.split(b":", 1)[1].strip())
            except ValueError: return None
    return None


def _default_client_capabilities() -> dict:
    return {
        "textDocument": {
            "synchronization": {
                "didSave": True, "willSave": False, "willSaveWaitUntil": False},
            "publishDiagnostics": {"relatedInformation": True},
            "hover": {"contentFormat": ["plaintext", "markdown"]},
            "definition": {"linkSupport": False},
        },
        "workspace": {"workspaceFolders": True, "configuration": False},
    }

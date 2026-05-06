"""LSP controller — drives `LSPClient` instances from editor state.

Owns one `LSPClient` per language id (lazily spawned on first file). When
LSP is enabled, the controller:
  - sends `textDocument/didOpen` on file load,
  - sends `textDocument/didChange` (full-document, debounced ~300 ms) on
    each editor edit,
  - sends `textDocument/didClose` on switch / reload,
  - routes `publishDiagnostics` notifications into `CodeViewer.set_diagnostics`,
  - exposes `request_hover()` for the active cursor position; the response
    is shown as a `QToolTip`.

Higher layer (MainWindow) wires this in. Gated by `DisplaySettings.lsp_enabled`.
"""
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QToolTip

from .lsp_client import LSPClient, to_uri


# language id → command spawning the server. The command must be on PATH
# or fully qualified. If the command isn't installed, _ensure_client emits
# a friendly status message and the feature is silently disabled for that
# language — the rest of LSP keeps working.
SERVERS = {
    "python":     ["pyright-langserver", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "javascript": ["typescript-language-server", "--stdio"],
    "go":         ["gopls"],
    "rust":       ["rust-analyzer"],
    "c":          ["clangd"],
    "cpp":        ["clangd"],
}

# TextView formats → LSP language ids.
FORMAT_TO_LANG = {
    "python":     "python",
    "typescript": "typescript",
    "javascript": "javascript",
    "go":         "go",
    "rust":       "rust",
    "c":          "c",
    "cpp":        "cpp",
}


class LSPController(QObject):
    """Per-window LSP coordinator. One client per language."""

    status = pyqtSignal(str)  # human-readable progress / error messages
    definition_resolved = pyqtSignal(str, int, int)  # path, line, character
    references_resolved = pyqtSignal(list)           # list of (path, line, char)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._clients: dict[str, LSPClient] = {}
        self._open_uris: dict[str, str] = {}    # uri → language_id
        self._versions: dict[str, int] = {}     # uri → monotonic int
        self._enabled = False
        self._definition_request_ids: set[int] = set()
        self._references_request_ids: set[int] = set()
        # Debounce timer for did_change: one shared instance.
        self._change_timer = QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(300)
        self._change_timer.timeout.connect(self._flush_pending_change)
        self._pending_change: tuple[str, str] | None = None  # (uri, text)

    # -- public API ----------------------------------------------------------

    def set_enabled(self, on: bool):
        self._enabled = bool(on)
        if not on: self.shutdown_all()

    def is_enabled(self) -> bool:
        return self._enabled

    def on_file_opened(self, path: str, fmt: str, text: str):
        if not self._enabled: return
        lang = FORMAT_TO_LANG.get(fmt)
        if lang is None: return
        client = self._ensure_client(lang)
        if client is None: return
        uri = to_uri(path)
        if uri in self._open_uris: return  # already opened
        version = self._versions.get(uri, 0) + 1
        self._versions[uri] = version
        self._open_uris[uri] = lang
        client.did_open(uri, lang, version, text)

    def on_text_changed(self, path: str, text: str):
        if not self._enabled: return
        uri = to_uri(path)
        if uri not in self._open_uris: return
        self._pending_change = (uri, text)
        self._change_timer.start()

    def on_file_closed(self, path: str):
        if not self._enabled: return
        uri = to_uri(path)
        lang = self._open_uris.pop(uri, None)
        if lang is None: return
        client = self._clients.get(lang)
        if client is not None and client.is_running():
            client.did_close(uri)

    def request_hover(self, path: str, line: int, character: int):
        if not self._enabled: return
        uri = to_uri(path)
        lang = self._open_uris.get(uri)
        if lang is None: return
        client = self._clients.get(lang)
        if client is None or not client.is_running(): return
        client.hover(uri, line, character)

    def request_definition(self, path: str, line: int, character: int):
        if not self._enabled: return
        uri = to_uri(path)
        lang = self._open_uris.get(uri)
        if lang is None: return
        client = self._clients.get(lang)
        if client is None or not client.is_running(): return
        rid = client.definition(uri, line, character)
        self._definition_request_ids.add(rid)

    def request_references(self, path: str, line: int, character: int):
        if not self._enabled: return
        uri = to_uri(path)
        lang = self._open_uris.get(uri)
        if lang is None: return
        client = self._clients.get(lang)
        if client is None or not client.is_running(): return
        rid = client.references(uri, line, character)
        self._references_request_ids.add(rid)

    def shutdown_all(self):
        if self._change_timer.isActive(): self._change_timer.stop()
        self._pending_change = None
        for client in self._clients.values():
            try: client.shutdown()
            except Exception: pass
        self._clients.clear()
        self._open_uris.clear()
        self._versions.clear()

    # -- internals -----------------------------------------------------------

    def _ensure_client(self, lang: str) -> LSPClient | None:
        client = self._clients.get(lang)
        if client is not None and client.is_running():
            return client
        cmd = SERVERS.get(lang)
        if not cmd: return None
        client = LSPClient(cmd, self)
        client.notification_received.connect(self._on_notification)
        client.response_received.connect(self._on_response)
        client.log.connect(lambda lvl, msg: self.status.emit(f"[{lang} {lvl}] {msg}"))
        if not client.start(root_uri=to_uri(str(Path.cwd()))):
            self.status.emit(f"Could not start {lang} server: {cmd[0]} (install or set lsp_enabled=False)")
            return None
        self._clients[lang] = client
        self.status.emit(f"Started {lang} language server.")
        return client

    def _flush_pending_change(self):
        if self._pending_change is None: return
        uri, text = self._pending_change
        self._pending_change = None
        lang = self._open_uris.get(uri)
        if lang is None: return
        client = self._clients.get(lang)
        if client is None or not client.is_running(): return
        version = self._versions.get(uri, 0) + 1
        self._versions[uri] = version
        client.did_change(uri, version, text)

    def _on_notification(self, method: str, params):
        if method == "textDocument/publishDiagnostics" and isinstance(params, dict):
            self._apply_diagnostics(params.get("uri", ""), params.get("diagnostics") or [])
        elif method == "window/showMessage" and isinstance(params, dict):
            self.status.emit(str(params.get("message", "")))

    def _on_response(self, request_id: int, result, error):
        if request_id in self._definition_request_ids:
            self._definition_request_ids.discard(request_id)
            self._handle_definition_result(result, error); return
        if request_id in self._references_request_ids:
            self._references_request_ids.discard(request_id)
            self._handle_references_result(result, error); return
        # Heuristic: hover responses have a `contents` key (string, MarkedString,
        # MarkupContent, or list of strings). Show the first textual chunk.
        if error is not None or not isinstance(result, dict): return
        contents = result.get("contents")
        text = _flatten_hover(contents)
        if text:
            QToolTip.showText(QCursor.pos(), text)

    def _handle_definition_result(self, result, error):
        if error is not None or result is None:
            self.status.emit("No definition found."); return
        loc = _first_location(result)
        if loc is None: self.status.emit("No definition found."); return
        uri, line, char = loc
        path = uri[7:] if uri.startswith("file://") else uri
        self.definition_resolved.emit(path, int(line), int(char))

    def _handle_references_result(self, result, error):
        if error is not None or not result:
            self.status.emit("No references found."); return
        locations = _all_locations(result if isinstance(result, list) else [result])
        if not locations:
            self.status.emit("No references found."); return
        out = []
        for uri, line, char in locations:
            path = uri[7:] if uri.startswith("file://") else uri
            out.append((path, int(line), int(char)))
        self.references_resolved.emit(out)

    def _apply_diagnostics(self, uri: str, diagnostics: list):
        # Only display diagnostics if the URI matches the active file.
        cur_path = getattr(self.window, "_current_path", None)
        if cur_path is None: return
        if to_uri(str(cur_path)) != uri: return
        viewer = getattr(self.window.viewer, "code", None)
        if viewer is not None and hasattr(viewer, "set_diagnostics"):
            viewer.set_diagnostics(diagnostics)
        panel = getattr(self.window, "diagnostics_panel", None)
        if panel is not None: panel.set_diagnostics(diagnostics)


def show_references_dialog(window, locations):
    """Modal listing every reference; activation jumps to the file+line."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
    )
    from pathlib import Path
    if not locations:
        window.statusBar().showMessage("No references found.", 4000); return
    dlg = QDialog(window); dlg.setWindowTitle(f"References ({len(locations)})")
    dlg.setModal(True); dlg.resize(640, 420)
    v = QVBoxLayout(dlg); v.setContentsMargins(8, 8, 8, 8)
    v.addWidget(QLabel(f"{len(locations)} reference(s):"))
    lst = QListWidget(); v.addWidget(lst, 1)
    cwd = Path.cwd()
    for path, line, char in locations:
        try: rel = str(Path(path).relative_to(cwd))
        except ValueError: rel = path
        item = QListWidgetItem(f"{rel}:{line + 1}:{char + 1}")
        item.setData(Qt.ItemDataRole.UserRole, (path, line, char))
        lst.addItem(item)
    if lst.count(): lst.setCurrentRow(0)
    def open_hit(item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            dlg.accept(); jump_to_definition(window, *data)
    lst.itemActivated.connect(open_hit)
    dlg.exec()


def jump_to_definition(window, path: str, line: int, character: int):
    """Open `path` in `window` (if not already current) and place the cursor
    at (line, character). Used as the controller's `definition_resolved`
    handler so MainWindow can stay thin."""
    from PyQt6.QtGui import QTextCursor
    if path != window._current_path:
        window.open_file(path)
    c = window.viewer.code.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    c.movePosition(QTextCursor.MoveOperation.Down, n=line)
    c.movePosition(QTextCursor.MoveOperation.Right, n=character)
    window.viewer.code.setTextCursor(c); window.viewer.code.centerCursor()


def _all_locations(items):
    """Same shapes as `_first_location` but returns every location in a
    list. Used for references — any of Location, Location[], LocationLink[]."""
    out = []
    for first in items:
        if not isinstance(first, dict): continue
        uri = first.get("uri") or first.get("targetUri")
        rng = first.get("range") or first.get("targetSelectionRange") or first.get("targetRange")
        if not uri or not isinstance(rng, dict): continue
        start = rng.get("start") or {}
        out.append((uri, start.get("line", 0), start.get("character", 0)))
    return out


def _first_location(result):
    """Extract (uri, line, character) from a definition response.

    LSP allows the result to be: a single Location, a Location[], a
    LocationLink[], or null. Pick the first usable hit; return None on
    miss or malformed shapes.
    """
    if isinstance(result, list):
        if not result: return None
        first = result[0]
    else:
        first = result
    if not isinstance(first, dict): return None
    uri = first.get("uri") or first.get("targetUri")
    rng = first.get("range") or first.get("targetSelectionRange") or first.get("targetRange")
    if not uri or not isinstance(rng, dict): return None
    start = rng.get("start") or {}
    return uri, start.get("line", 0), start.get("character", 0)


def _flatten_hover(contents) -> str:
    if contents is None: return ""
    if isinstance(contents, str): return contents
    if isinstance(contents, dict):
        if "value" in contents: return str(contents["value"])
        if "language" in contents and "value" in contents:
            return str(contents["value"])
    if isinstance(contents, list):
        chunks = []
        for c in contents:
            t = _flatten_hover(c)
            if t: chunks.append(t)
        return "\n\n".join(chunks)
    return str(contents)

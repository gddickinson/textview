"""Jupyter notebook viewer + runner.

Loads a `.ipynb` via `nbformat`, renders one widget per cell (markdown
rendered to HTML, code cells with input + a Run button + output area),
and dispatches `Run` to a shared `KernelHost`. Cell outputs from the
kernel route back to the cell that issued the request.

Cells are display-only (no input editing) in this first iteration —
load, run, save outputs back. Editing cell sources is the natural next
step but kept out of scope here to ship.
"""
from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QTextBrowser, QScrollArea, QFrame, QSizePolicy,
)

from .notebook_kernel import KernelHost


_MONO = "Menlo, Consolas, monospace"


def _mono_font() -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(11)
    return f


class CellWidget(QFrame):
    """One notebook cell — input + (for code cells) output."""

    run_requested = pyqtSignal(object)        # emits self
    source_changed = pyqtSignal(object)       # emits self when input edited
    type_change_requested = pyqtSignal(object, str)  # (self, new_type)

    def __init__(self, cell_dict: dict, index: int, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.cell = cell_dict
        self.index = index
        self.cell_type = cell_dict.get("cell_type", "code")
        self._msg_id: str = ""
        self._live_outputs: list[dict] = []  # accumulated nbformat-shape outputs
        v = QVBoxLayout(self); v.setContentsMargins(6, 4, 6, 4); v.setSpacing(4)

        hdr = QHBoxLayout()
        if self.cell_type == "code":
            n = cell_dict.get("execution_count")
            self.lbl_kind = QLabel(f"In [{n if n else ' '}]:")
            self.lbl_kind.setStyleSheet("color: #1976d2; font-family: monospace;")
        else:
            self.lbl_kind = QLabel(f"[{self.cell_type}]")
            self.lbl_kind.setStyleSheet("color: #888;")
        hdr.addWidget(self.lbl_kind); hdr.addStretch(1)
        if self.cell_type == "code":
            self.btn_run = QPushButton("▶ Run"); self.btn_run.setFixedWidth(70)
            self.btn_run.clicked.connect(lambda: self.run_requested.emit(self))
            hdr.addWidget(self.btn_run)
        else:
            self.btn_edit = QPushButton("Edit"); self.btn_edit.setFixedWidth(70); self.btn_edit.setCheckable(True)
            self.btn_edit.toggled.connect(self._toggle_markdown_edit)
            hdr.addWidget(self.btn_edit)
        v.addLayout(hdr)

        source = "".join(cell_dict.get("source") or [])
        if self.cell_type == "markdown":
            self._md_source = source
            self.body = QTextBrowser(); self.body.setOpenExternalLinks(True)
            self.body.setMarkdown(source)
            self.body.setMaximumHeight(self._heuristic_height(source))
            v.addWidget(self.body)
            self.editor: QPlainTextEdit | None = None  # lazy; built on first edit
        else:
            self.body = QPlainTextEdit(); self.body.setReadOnly(False)
            self.body.setFont(_mono_font())
            self.body.setPlainText(source)
            self.body.setStyleSheet(f"font-family: {_MONO};")
            self.body.setMaximumHeight(self._heuristic_height(source))
            self.body.textChanged.connect(self._on_source_changed)
            v.addWidget(self.body)
            self.output = QTextBrowser()
            self.output.setStyleSheet(f"font-family: {_MONO}; background: #fafafa;")
            self.output.setOpenExternalLinks(True)
            self.output.setMaximumHeight(220)
            self.output.setVisible(False)
            v.addWidget(self.output)
            self._populate_initial_outputs()

    def _heuristic_height(self, text: str) -> int:
        lines = max(1, text.count("\n") + 1)
        return min(360, 24 + lines * 18)

    def _populate_initial_outputs(self):
        """Render outputs already saved in the .ipynb at load time."""
        outs = self.cell.get("outputs") or []
        chunks = [_format_output(o) for o in outs if _format_output(o)]
        if chunks:
            self.output.setHtml("".join(chunks))
            self.output.setVisible(True)

    # -- live output handling -----------------------------------------------

    def begin_run(self, msg_id: str):
        self._msg_id = msg_id
        if self.cell_type != "code": return
        self._live_outputs = []
        self._output_html: list[str] = []  # accumulated raw HTML chunks
        self.lbl_kind.setText("In [*]:")
        self.output.setVisible(True)
        self.output.setHtml("<pre style='color:#888'>(running…)</pre>")

    def append_output(self, msg: dict):
        if self.cell_type != "code": return
        self._live_outputs.append(_iopub_to_nbformat(msg))
        chunk = _format_output_msg(msg)
        if not chunk: return
        # Round-tripping through `toHtml()` adds Qt's <html>… shell — feeding
        # that back via setHtml + raw <pre> drops trailing chars. Keep raw
        # chunks and rebuild from scratch.
        if not hasattr(self, "_output_html"): self._output_html = []
        self._output_html.append(chunk)
        self.output.setHtml("".join(self._output_html))
        self.output.setMaximumHeight(360)

    def show_error(self, text: str):
        """Display a one-line error in the output area (used when kernel
        startup fails or a request is rejected before execution begins)."""
        if self.cell_type != "code": return
        self.output.setVisible(True)
        self.output.setHtml(f"<pre style='color:#c62828'>{_escape(text)}</pre>")

    def end_run(self):
        if self.cell_type != "code": return
        self.cell["outputs"] = self._live_outputs
        # Best-effort execution-count bump: take it from any execute_result
        # output if present, else just increment whatever was there before.
        ec = next((o.get("execution_count") for o in self._live_outputs
                   if o.get("output_type") == "execute_result"
                   and o.get("execution_count") is not None), None)
        if ec is None:
            prev = self.cell.get("execution_count") or 0
            ec = prev + 1
        self.cell["execution_count"] = ec
        self.lbl_kind.setText(f"In [{ec}]:")
        cur = self.output.toHtml()
        if "(running…)" in cur:
            self.output.setHtml("<pre style='color:#888'>(no output)</pre>")
        self.source_changed.emit(self)

    def _on_source_changed(self):
        if self.cell_type == "code":
            self.cell["source"] = self.body.toPlainText()
            self.source_changed.emit(self)

    def _toggle_markdown_edit(self, on: bool):
        """Swap the rendered QTextBrowser for a QPlainTextEdit and back."""
        layout = self.layout()
        if on:
            if self.editor is None:
                self.editor = QPlainTextEdit(); self.editor.setFont(_mono_font())
                self.editor.setStyleSheet(f"font-family: {_MONO};")
                self.editor.textChanged.connect(self._on_md_source_changed)
            self.editor.setPlainText(self._md_source)
            self.editor.setMaximumHeight(self._heuristic_height(self._md_source))
            layout.replaceWidget(self.body, self.editor)
            self.body.hide(); self.editor.show()
            self.btn_edit.setText("Done")
        else:
            self._md_source = self.editor.toPlainText() if self.editor else self._md_source
            self.body.setMarkdown(self._md_source)
            self.body.setMaximumHeight(self._heuristic_height(self._md_source))
            layout.replaceWidget(self.editor, self.body)
            self.editor.hide(); self.body.show()
            self.btn_edit.setText("Edit")
            self.cell["source"] = self._md_source
            self.source_changed.emit(self)

    def _on_md_source_changed(self):
        if self.editor is not None:
            self._md_source = self.editor.toPlainText()
            self.cell["source"] = self._md_source
            self.source_changed.emit(self)


def _format_output_msg(msg: dict) -> str:
    """Format a live iopub message (one of stream/execute_result/display_data/error)."""
    msg_type = msg.get("msg_type")
    content = msg.get("content") or {}
    if msg_type == "stream":
        return f"<pre>{_escape(content.get('text', ''))}</pre>"
    if msg_type in ("execute_result", "display_data"):
        return _render_data_bundle(content.get("data") or {})
    if msg_type == "error":
        return f"<pre style='color:#c62828'>{_escape(_render_traceback(content))}</pre>"
    return ""


def _format_output(out: dict) -> str:
    """Format a saved nbformat output object (different shape than iopub msg)."""
    t = out.get("output_type")
    if t == "stream":
        text = "".join(out.get("text") or []) if isinstance(out.get("text"), list) else str(out.get("text") or "")
        return f"<pre>{_escape(text)}</pre>"
    if t in ("execute_result", "display_data"):
        return _render_data_bundle(out.get("data") or {})
    if t == "error":
        tb = "\n".join(out.get("traceback") or [])
        return f"<pre style='color:#c62828'>{_escape(tb)}</pre>"
    return ""


# Mime-type priority: richer first, falling back to plain text.
_MIME_PRIORITY = (
    "text/html", "image/svg+xml", "image/png", "image/jpeg",
    "text/markdown", "text/plain",
)


def _render_data_bundle(data: dict) -> str:
    """Render the highest-priority MIME type from an output `data` bundle."""
    if not data: return ""
    for mime in _MIME_PRIORITY:
        if mime in data:
            return _render_one_mime(mime, data[mime])
    # Fallback: first key
    k = next(iter(data))
    return _render_one_mime(k, data[k])


def _render_one_mime(mime: str, payload) -> str:
    """nbformat lists for text bundles, str for binary; normalize."""
    if isinstance(payload, list):
        text = "".join(payload)
    else:
        text = str(payload)
    if mime == "text/plain":
        return f"<pre>{_escape(text)}</pre>"
    if mime == "text/html":
        return text  # trust the kernel; QTextBrowser renders a safe subset
    if mime == "text/markdown":
        # QTextBrowser supports markdown via setMarkdown but here we're
        # building inline HTML — escape and wrap as <pre> rather than fail.
        return f"<pre>{_escape(text)}</pre>"
    if mime == "image/svg+xml":
        return text  # QTextBrowser handles inline SVG
    if mime in ("image/png", "image/jpeg"):
        # Already base64-encoded by nbformat.
        return f'<img src="data:{mime};base64,{text.strip()}" />'
    return f"<pre>{_escape(text)}</pre>"


def _render_traceback(content: dict) -> str:
    tb = content.get("traceback") or []
    return "\n".join(tb) if tb else f"{content.get('ename', '')}: {content.get('evalue', '')}"


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _new_cell_dict(cell_type: str, source: str = "") -> dict:
    """Minimal nbformat-compatible cell dict. nbformat will fill in `id`
    and other required fields when validating during write."""
    base = {"cell_type": cell_type, "metadata": {}, "source": source}
    if cell_type == "code":
        base["execution_count"] = None
        base["outputs"] = []
    return base


def _iopub_to_nbformat(msg: dict) -> dict:
    """Convert one live iopub message into an nbformat-shaped output dict."""
    msg_type = msg.get("msg_type"); content = msg.get("content") or {}
    if msg_type == "stream":
        return {"output_type": "stream",
                "name": content.get("name", "stdout"),
                "text": content.get("text", "")}
    if msg_type == "execute_result":
        return {"output_type": "execute_result",
                "data": content.get("data") or {},
                "metadata": content.get("metadata") or {},
                "execution_count": content.get("execution_count")}
    if msg_type == "display_data":
        return {"output_type": "display_data",
                "data": content.get("data") or {},
                "metadata": content.get("metadata") or {}}
    if msg_type == "error":
        return {"output_type": "error",
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback") or []}
    return {"output_type": msg_type or "unknown"}


class NotebookView(QScrollArea):
    """Scrolling list of cell widgets backed by a shared kernel."""

    dirty_changed = pyqtSignal(bool)
    status = pyqtSignal(str)        # human-readable progress / error messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body); self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8); self._layout.addStretch(1)
        self.setWidget(self._body)
        self._cells: list[CellWidget] = []
        self._kernel = KernelHost(self)
        self._notebook = None  # nbformat NotebookNode
        self._path: str | None = None
        self._dirty = False
        self._default_interpreter = "python3"
        self._kernel.output.connect(self._route_output)
        self._kernel.execute_complete.connect(self._route_complete)
        self._msg_to_cell: dict[str, CellWidget] = {}

    def set_default_interpreter(self, interpreter: str):
        """Used when auto-starting the kernel from a Run click."""
        if interpreter: self._default_interpreter = interpreter

    def kernel(self) -> KernelHost:
        return self._kernel

    def load(self, path: str) -> bool:
        try:
            import nbformat
            nb = nbformat.read(path, as_version=4)
        except Exception:
            return False
        self._notebook = nb; self._path = path
        for cell in self._cells: cell.setParent(None)
        self._cells.clear(); self._msg_to_cell.clear()
        for i, cell in enumerate(nb.get("cells") or []):
            self._add_cell_widget(cell, i)
        self._set_dirty(False)
        return True

    def save(self, path: str | None = None) -> bool:
        target = path or self._path
        if target is None or self._notebook is None: return False
        try:
            import nbformat
            # nbformat write requires NotebookNode-shaped cells; wrap any
            # plain dicts (e.g. cells added via add_cell) to satisfy
            # `cell.cell_type` attribute access in `split_lines`.
            self._notebook["cells"] = [nbformat.from_dict(w.cell) for w in self._cells]
            nbformat.write(self._notebook, target)
        except Exception:
            return False
        self._path = target
        self._set_dirty(False)
        return True

    def is_dirty(self) -> bool: return self._dirty
    def path(self) -> str | None: return self._path

    def _set_dirty(self, on: bool):
        if on != self._dirty:
            self._dirty = on; self.dirty_changed.emit(on)

    def _add_cell_widget(self, cell_dict: dict, index: int) -> "CellWidget":
        w = CellWidget(cell_dict, index)
        w.run_requested.connect(self._run_cell)
        w.source_changed.connect(lambda _c: self._set_dirty(True))
        self._layout.insertWidget(self._layout.count() - 1, w)
        self._cells.insert(index, w)
        for i, c in enumerate(self._cells): c.index = i
        return w

    def cell_count(self) -> int:
        return len(self._cells)

    def cells(self) -> list[CellWidget]:
        return list(self._cells)

    def current_cell(self) -> "CellWidget | None":
        """Cell whose source widget currently has keyboard focus."""
        from PyQt6.QtWidgets import QApplication
        fw = QApplication.focusWidget()
        if fw is None: return None
        for c in self._cells:
            if fw is c.body or (c.editor is not None and fw is c.editor):
                return c
        return None

    def index_of(self, cell: "CellWidget") -> int:
        try: return self._cells.index(cell)
        except ValueError: return -1

    def start_kernel(self, interpreter: str = "python3") -> bool:
        return self._kernel.start(interpreter)

    def run_all(self):
        if not self._ensure_kernel(): return
        for c in self._cells:
            if c.cell_type == "code":
                self._run_cell(c)

    def shutdown(self):
        self._kernel.shutdown()

    def _ensure_kernel(self) -> bool:
        """Start kernel on first use. Tries `_default_interpreter`, falls back
        to `sys.executable`. `last_error` from the kernel host surfaces the
        actual cause (sqlite ABI break, missing ipykernel, etc.)."""
        import sys
        if self._kernel.is_running(): return True
        self.status.emit(f"Starting kernel ({self._default_interpreter})…")
        if self._kernel.start(self._default_interpreter):
            self.status.emit(f"Kernel started ({self._default_interpreter})."); return True
        first_err = self._kernel.last_error
        if self._default_interpreter != sys.executable:
            self.status.emit(f"Falling back to {sys.executable} (the app's own Python)…")
            if self._kernel.start(sys.executable):
                self.status.emit(f"Kernel started ({sys.executable})."); return True
        err = self._kernel.last_error or first_err or "(unknown error)"
        self.status.emit(f"Could not start kernel: {err}")
        return False

    def last_error(self) -> str: return self._kernel.last_error

    def _run_cell(self, cell: CellWidget):
        if not self._ensure_kernel():
            err = self.last_error() or "kernel not running"
            cell.show_error(f"Kernel could not start.\n{err}"); return
        source = cell.body.toPlainText() if hasattr(cell.body, "toPlainText") else ""
        msg_id = self._kernel.execute(source)
        if not msg_id:
            cell.show_error("Kernel did not accept the request."); return
        self._msg_to_cell[msg_id] = cell
        cell.begin_run(msg_id)

    def _route_output(self, msg_id: str, msg: dict):
        cell = self._msg_to_cell.get(msg_id)
        if cell is not None: cell.append_output(msg)

    def _route_complete(self, msg_id: str):
        cell = self._msg_to_cell.pop(msg_id, None)
        if cell is not None:
            cell.end_run(); self._set_dirty(True)

    # -- cell mutation -------------------------------------------------------

    def add_cell(self, after_index: int = -1, cell_type: str = "code") -> "CellWidget":
        new_cell = _new_cell_dict(cell_type)
        idx = (after_index + 1) if after_index >= 0 else len(self._cells)
        w = self._add_cell_widget(new_cell, idx)
        self._set_dirty(True)
        return w

    def delete_cell(self, index: int) -> bool:
        if not (0 <= index < len(self._cells)): return False
        w = self._cells.pop(index); w.setParent(None)
        for i, c in enumerate(self._cells): c.index = i
        self._set_dirty(True)
        return True

    def change_cell_type(self, index: int, new_type: str) -> bool:
        if not (0 <= index < len(self._cells)): return False
        if new_type not in ("code", "markdown", "raw"): return False
        old = self._cells[index]
        if old.cell_type == new_type: return False
        # Capture current source from the live widget.
        if old.cell_type == "code":
            src = old.body.toPlainText()
        elif old.editor is not None and old.btn_edit.isChecked():
            src = old.editor.toPlainText()
        else:
            src = old._md_source if old.cell_type == "markdown" else "".join(old.cell.get("source") or [])
        new_dict = _new_cell_dict(new_type, source=src)
        self._cells.pop(index); old.setParent(None)
        self._add_cell_widget(new_dict, index)
        self._set_dirty(True)
        return True

    def move_cell(self, index: int, direction: int) -> bool:
        """direction = -1 (up) or +1 (down)."""
        if not (0 <= index < len(self._cells)): return False
        target = index + (1 if direction > 0 else -1)
        if not (0 <= target < len(self._cells)): return False
        # Swap in `_cells` and re-position in the QVBoxLayout.
        self._cells[index], self._cells[target] = self._cells[target], self._cells[index]
        # Re-insert widgets in the new order (the layout doesn't have a swap op).
        for w in self._cells:
            self._layout.removeWidget(w)
        # Strip the trailing stretch and re-add cells before re-adding stretch.
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is None and item.spacerItem() is not None: break
        for w in self._cells:
            self._layout.addWidget(w)
        self._layout.addStretch(1)
        for i, c in enumerate(self._cells): c.index = i
        self._set_dirty(True)
        return True

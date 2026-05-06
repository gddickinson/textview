"""Inline LLM suggestions — phase 1 (on-demand).

Trigger via `Alt+/`. The active LLM provider (whatever the chat panel is
configured for) gets a one-shot completion request. The response is
inserted into the buffer at the cursor with a faded character format
(grey + italic) so it reads as a suggestion. **Tab** accepts (clears the
faded format and advances the cursor past the suggestion). **Esc**
rejects (deletes the suggestion). Any other key also rejects and is
processed normally.

This is the minimum-viable Copilot-shaped feature: no auto-debounce, no
multi-line ghosting overlay. Phase 2 would add request-on-pause and a
real overlay (so accidental edits to selected text don't accidentally
keep ghost characters).
"""
from PyQt6.QtCore import (
    QObject, QThread, pyqtSignal, QEvent, Qt,
)
from PyQt6.QtGui import QTextCharFormat, QTextCursor, QColor

from .llm.factory import make_provider
from .llm.base import Message, TextChunk, ToolCall, Done, Error


_MAX_PREFIX = 4000   # chars of context before the cursor we send to the model
_MAX_SUFFIX = 1000   # chars after the cursor (smaller — fits-in-the-middle hint)
_MAX_TOKENS = 200
_TEMPERATURE = 0.2

_SYSTEM = (
    "You are a code-completion assistant. The user's file is delimited by "
    "<file> tags; the cursor location is marked <CURSOR>. Output ONLY the "
    "text that should be inserted at <CURSOR> — nothing before it, no code "
    "fences, no commentary. Match the surrounding indentation. Stop at a "
    "natural breakpoint (end of line, end of expression, end of block)."
)


class CompletionWorker(QObject):
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, provider, system: str, user: str, model: str | None = None):
        super().__init__()
        self.provider = provider
        self.system = system
        self.user = user
        self.model = model

    def run(self):
        try:
            messages = [Message(role="user", content=self.user)]
            text = ""
            for ev in self.provider.chat_stream(
                messages, system=self.system, model=self.model,
                max_tokens=_MAX_TOKENS, temperature=_TEMPERATURE,
            ):
                if isinstance(ev, TextChunk):
                    text += ev.text
                elif isinstance(ev, ToolCall):
                    pass  # ignore — completions don't expect tools
                elif isinstance(ev, Done):
                    break
                elif isinstance(ev, Error):
                    self.failed.emit(ev.detail)
                    return
            self.completed.emit(_strip_fences(text))
        except Exception as e:
            self.failed.emit(str(e))


def _strip_fences(text: str) -> str:
    """Models occasionally wrap output in ```lang fences despite instructions.
    Strip them so the buffer doesn't grow stray backticks."""
    s = text.strip("\n")
    if s.startswith("```"):
        lines = s.split("\n")
        if len(lines) >= 2:
            end = -1 if lines[-1].strip() == "```" else len(lines)
            return "\n".join(lines[1:end])
    return s


class InlineSuggester(QObject):
    """Owns the request lifecycle and the in-buffer ghost-text state."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._anchor: int = -1     # buffer position where the ghost starts
        self._length: int = 0      # chars of pending suggestion in the buffer
        self._pending: bool = False  # request in flight, no ghost yet
        self._inserting: bool = False  # internal-edit guard
        self._thread: QThread | None = None
        self._worker: CompletionWorker | None = None
        # Intercept Tab / Esc / any key while a ghost is visible.
        window.viewer.code.installEventFilter(self)

    # -- request -------------------------------------------------------------

    def request(self):
        if self._pending or self._length > 0:
            return  # already in flight or already showing a ghost
        code = self.window.viewer.code
        if code.isReadOnly():
            self.window.statusBar().showMessage(
                "Enable edit mode (Ctrl+E) for inline suggestions.", 3000)
            return
        d = self.window.settings_manager.display
        prov = make_provider(d)
        ok, why = prov.is_available()
        if not ok:
            self.window.statusBar().showMessage(f"LLM not available: {why}", 4000)
            return

        text = code.toPlainText()
        cur = code.textCursor()
        pos = cur.position()
        prefix = text[:pos]
        suffix = text[pos:]
        if len(prefix) > _MAX_PREFIX:
            prefix = "…" + prefix[-_MAX_PREFIX:]
        if len(suffix) > _MAX_SUFFIX:
            suffix = suffix[:_MAX_SUFFIX] + "…"
        user_msg = (
            f"<file format='{self.window._current_format or 'text'}'>\n"
            f"{prefix}<CURSOR>{suffix}\n</file>"
        )

        from .llm.factory import model_for
        self._anchor = pos
        self._pending = True
        self.window.statusBar().showMessage(
            f"Suggesting via {prov.name} ({model_for(d)})…", 5000)

        self._thread = QThread()
        self._worker = CompletionWorker(prov, _SYSTEM, user_msg, model=model_for(d))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    # -- worker callbacks ----------------------------------------------------

    def _on_completed(self, text: str):
        self._pending = False
        if not text:
            self.window.statusBar().showMessage("(empty suggestion)", 3000)
            self._cleanup_thread()
            return
        code = self.window.viewer.code
        # Has the user moved the cursor since we asked? If so, drop.
        if code.textCursor().position() != self._anchor:
            self.window.statusBar().showMessage(
                "Suggestion dropped — cursor moved during request.", 4000)
            self._cleanup_thread()
            return
        cur = QTextCursor(code.document())
        cur.setPosition(self._anchor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#888888"))
        fmt.setFontItalic(True)
        self._inserting = True
        cur.insertText(text, fmt)
        self._inserting = False
        self._length = len(text)
        # Park the cursor at the anchor so the user can Tab-to-accept or
        # keep typing.
        cur.setPosition(self._anchor)
        code.setTextCursor(cur)
        self.window.statusBar().showMessage(
            f"Tab to accept · Esc to dismiss · {len(text)} chars from "
            f"the model.", 5000)
        self._cleanup_thread()

    def _on_failed(self, msg: str):
        self._pending = False
        self.window.statusBar().showMessage(
            f"Suggestion failed: {msg[:160]}", 5000)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(500)
            self._thread = None
        self._worker = None

    # -- accept / reject -----------------------------------------------------

    def accept(self):
        if self._length <= 0:
            return
        code = self.window.viewer.code
        cur = QTextCursor(code.document())
        cur.setPosition(self._anchor)
        cur.setPosition(self._anchor + self._length,
                        QTextCursor.MoveMode.KeepAnchor)
        self._inserting = True
        cur.setCharFormat(QTextCharFormat())   # de-faded
        self._inserting = False
        cur.setPosition(self._anchor + self._length)
        code.setTextCursor(cur)
        self._reset_state()

    def reject(self):
        if self._length <= 0:
            return
        code = self.window.viewer.code
        cur = QTextCursor(code.document())
        cur.setPosition(self._anchor)
        cur.setPosition(self._anchor + self._length,
                        QTextCursor.MoveMode.KeepAnchor)
        self._inserting = True
        cur.removeSelectedText()
        self._inserting = False
        self._reset_state()

    def _reset_state(self):
        self._anchor = -1
        self._length = 0

    # -- key interception ----------------------------------------------------

    def eventFilter(self, obj, event):
        if (obj is self.window.viewer.code
                and event.type() == QEvent.Type.KeyPress
                and self._length > 0):
            key = event.key()
            if key == Qt.Key.Key_Tab:
                self.accept()
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
            # Any other key cancels the suggestion and is processed normally.
            self.reject()
            return False
        return False

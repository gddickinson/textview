"""Chat panel — talk to Claude / Ollama from inside the viewer.

Phase 1: streaming chat, no tool use yet. Conversations live in memory
for the session; per-message markdown rendered live as tokens arrive.
The worker runs on a `QThread` so the UI stays responsive while a long
response streams in.
"""
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QShortcut, QKeySequence, QFont
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QPlainTextEdit, QTextBrowser, QComboBox, QCheckBox, QInputDialog,
    QMessageBox, QSizePolicy,
)

from .llm.base import Message, TextChunk, ToolCall, Done, Error
from .llm.factory import make_provider, model_for, PROVIDERS
from .llm.conversation import Conversation
from .llm import credentials, audit
from .llm.tools import find_tool, specs_for, ACTION_TOOLS
from .chat_render import render_transcript


class StreamWorker(QObject):
    chunk = pyqtSignal(str)
    tool_call = pyqtSignal(object)   # ToolCall instance
    done = pyqtSignal(dict, str)     # usage, stop_reason
    error = pyqtSignal(str, str)     # kind, detail

    def __init__(self, provider, messages, system, model, max_tokens,
                 temperature, tools=None):
        super().__init__()
        self.provider = provider
        self.messages = messages
        self.system = system
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.tools = tools
        self._stop = False

    def run(self):
        try:
            for ev in self.provider.chat_stream(
                self.messages, system=self.system, model=self.model,
                max_tokens=self.max_tokens, temperature=self.temperature,
                tools=self.tools,
            ):
                if self._stop:
                    break
                if isinstance(ev, TextChunk):
                    self.chunk.emit(ev.text)
                elif isinstance(ev, ToolCall):
                    self.tool_call.emit(ev)
                elif isinstance(ev, Done):
                    self.done.emit(ev.usage, ev.stop_reason)
                    return
                elif isinstance(ev, Error):
                    self.error.emit(ev.kind, ev.detail)
                    return
            self.done.emit({}, "stopped")
        except Exception as e:
            self.error.emit("internal", str(e))

    def stop(self):
        self._stop = True


class ChatPanel(QDockWidget):
    def __init__(self, window):
        super().__init__("Chat", window)
        self.window = window
        self.conv = Conversation()
        self._worker: StreamWorker | None = None
        self._thread: QThread | None = None
        self._streaming_buffer = ""
        self._pending_tool_calls: list[ToolCall] = []
        self._agent_steps = 0
        self._build_ui()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        v.addWidget(self._build_header())

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v.addWidget(self.transcript, 1)

        v.addWidget(self._build_input_bar())
        self.setWidget(root)
        self.setMinimumWidth(360)
        self._render_transcript()

    def _build_header(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.cb_provider = QComboBox()
        self.cb_provider.addItems(list(PROVIDERS))
        self.cb_provider.currentTextChanged.connect(self._on_provider_changed)
        h.addWidget(QLabel("Provider:"))
        h.addWidget(self.cb_provider)
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)
        self.cb_model.setMinimumWidth(220)
        self.cb_model.currentTextChanged.connect(self._on_model_changed)
        h.addWidget(QLabel("Model:"))
        h.addWidget(self.cb_model, 1)
        self.btn_refresh_models = QPushButton("⟳")
        self.btn_refresh_models.setToolTip(
            "Refresh model list (re-queries Ollama / refreshes cloud presets).")
        self.btn_refresh_models.setFixedWidth(28)
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        h.addWidget(self.btn_refresh_models)
        self.btn_set_key = QPushButton("API key…")
        self.btn_set_key.clicked.connect(self._on_set_key)
        h.addWidget(self.btn_set_key)
        self.btn_new = QPushButton("New chat")
        self.btn_new.clicked.connect(self._on_new_chat)
        h.addWidget(self.btn_new)
        return bar

    def _build_input_bar(self):
        bar = QWidget()
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        opts = QHBoxLayout()
        opts.setContentsMargins(0, 0, 0, 0)
        opts.setSpacing(12)
        self.cb_send_context = QCheckBox("Include current file in prompt")
        self.cb_send_context.setToolTip(
            "When checked, the path + extracted text of the open file is "
            "added as a system note. Off by default — content stays local "
            "unless you opt in."
        )
        opts.addWidget(self.cb_send_context)
        self.cb_agent = QCheckBox("Agent mode (lets Claude read/inspect files)")
        self.cb_agent.setToolTip(
            "When checked, the model can call read-only tools "
            "(open_file, search_in_file, list_dir, get_metadata, …). "
            "Tool calls and their results are shown in the transcript and "
            "logged to ~/.local/share/TextView/llm_audit.jsonl."
        )
        self.cb_agent.toggled.connect(
            lambda v: self.window.settings_manager.update("llm_agent_mode", v)
        )
        opts.addWidget(self.cb_agent)
        self.cb_actions = QCheckBox("Allow actions")
        self.cb_actions.setToolTip(
            "When on, action tools (replace_selection, insert_text, save, "
            "run_command, run_python, take_screenshot, change_setting) are "
            "also offered to the agent. Each destructive call still asks "
            "for confirmation unless 'Trust this conversation' is set."
        )
        self.cb_actions.toggled.connect(
            lambda v: self.window.settings_manager.update("llm_agent_actions", v)
        )
        opts.addWidget(self.cb_actions)
        opts.addStretch(); opts_w = QWidget(); opts_w.setLayout(opts); v.addWidget(opts_w)
        row = QWidget(); h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
        self.input = QPlainTextEdit(); self.input.setPlaceholderText("Message Claude…  (Ctrl+Enter to send)"); self.input.setFixedHeight(80)
        f = QFont("Menlo"); f.setStyleHint(QFont.StyleHint.Monospace); f.setPointSize(11)
        self.input.setFont(f); h.addWidget(self.input, 1); self.input.setAcceptDrops(True); self.input.dragEnterEvent = self._drag_enter; self.input.dropEvent = self._drop
        col = QVBoxLayout(); col.setSpacing(4)
        self.btn_send = QPushButton("Send"); self.btn_send.clicked.connect(self._on_send); col.addWidget(self.btn_send)
        self.btn_attach = QPushButton("📎 Image"); self.btn_attach.setToolTip("Attach an image to the next message"); self.btn_attach.clicked.connect(self._on_attach); col.addWidget(self.btn_attach)
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self._on_stop); self.btn_stop.setEnabled(False); col.addWidget(self.btn_stop)
        self._pending_attachments: list[str] = []
        h.addLayout(col); v.addWidget(row)
        self.lbl_status = QLabel("Ready"); self.lbl_status.setStyleSheet("color: #888;"); v.addWidget(self.lbl_status)
        QShortcut(QKeySequence("Ctrl+Return"), self.input, activated=self._on_send); return bar

    # -- public API ----------------------------------------------------------

    def sync_from_settings(self):
        d = self.window.settings_manager.display
        self.cb_provider.blockSignals(True)
        self.cb_provider.setCurrentText(d.llm_provider)
        self.cb_provider.blockSignals(False)
        self.cb_agent.blockSignals(True)
        self.cb_agent.setChecked(d.llm_agent_mode)
        self.cb_agent.blockSignals(False)
        self.cb_actions.blockSignals(True)
        self.cb_actions.setChecked(d.llm_agent_actions)
        self.cb_actions.blockSignals(False)
        self._refresh_models()

    def _refresh_models(self):
        d = self.window.settings_manager.display
        provider_name = self.cb_provider.currentText()
        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        if provider_name == "anthropic":
            self.cb_model.addItems([
                "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
            ])
            self.cb_model.setCurrentText(d.llm_model_anthropic)
        elif provider_name == "openai":
            self.cb_model.addItems([
                "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
            ])
            self.cb_model.setCurrentText(d.llm_model_openai)
        else:
            from .llm.ollama_provider import OllamaProvider
            try:
                models = OllamaProvider(d.llm_ollama_url).list_models()
            except Exception:
                models = []
            if not models:
                models = ["llama3.1:8b", "qwen2.5:7b", "mistral:7b"]
            self.cb_model.addItems(models)
            self.cb_model.setCurrentText(d.llm_model_ollama)
        self.cb_model.blockSignals(False)

    # -- event handlers ------------------------------------------------------

    def _on_provider_changed(self, name: str):
        self.window.settings_manager.update("llm_provider", name)
        self._refresh_models()

    def _on_model_changed(self, name: str):
        d = self.window.settings_manager.display
        key = {
            "anthropic": "llm_model_anthropic",
            "openai": "llm_model_openai",
            "ollama": "llm_model_ollama",
        }.get(d.llm_provider, "llm_model_anthropic")
        self.window.settings_manager.update(key, name)

    def _on_set_key(self):
        provider = self.cb_provider.currentText()
        existing = credentials.get_api_key(provider) or ""
        masked = ("•" * 12 + existing[-4:]) if existing else ""
        text, ok = QInputDialog.getText(
            self.window, f"Set {provider} API key",
            f"API key (leave empty to clear).\nCurrently: {masked or '(none)'}",
        )
        if not ok:
            return
        if not text.strip():
            credentials.clear_api_key(provider)
            self.lbl_status.setText(f"Cleared {provider} key.")
        else:
            where = credentials.set_api_key(provider, text.strip())
            self.lbl_status.setText(f"Stored {provider} key in {where}.")

    def _on_new_chat(self):
        if self._worker:
            self._on_stop()
        self.conv.reset()
        self._conv_trusted = False
        self._render_transcript()
        self.lbl_status.setText("New chat.")

    def _drag_enter(self, ev): ev.mimeData().hasUrls() and ev.acceptProposedAction()
    def _drop(self, ev):
        from .chat_attachments import _SUPPORTED
        imgs = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile() and any(u.toLocalFile().lower().endswith(e) for e in _SUPPORTED)]
        if imgs: self._add_attachments(imgs); ev.acceptProposedAction()

    def _on_attach(self):
        from PyQt6.QtWidgets import QFileDialog; from .chat_attachments import _SUPPORTED
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach image(s)", "", "Images (" + " ".join(f"*{e}" for e in _SUPPORTED) + ")")
        if paths: self._add_attachments(paths)
    def _add_attachments(self, paths):
        self._pending_attachments.extend(paths); n = len(self._pending_attachments)
        self.btn_attach.setText(f"📎 Image ({n})"); self.lbl_status.setText(f"{n} image(s) attached to next message.")

    def _on_send(self):
        if self._worker is not None: return
        text = self.input.toPlainText().strip()
        if not text and not self._pending_attachments: return
        d = self.window.settings_manager.display; prov = make_provider(d)
        ok, why = prov.is_available()
        if not ok: QMessageBox.warning(self.window, "Provider unavailable", why); return
        self._sys_prompt = self._compose_system_prompt(d)
        from .chat_attachments import build_user_content, to_openai_content
        content = build_user_content(text, self._pending_attachments)
        if d.llm_provider == "openai" and isinstance(content, list):
            content = to_openai_content(content)
        self.conv.add("user", content)
        self._pending_attachments = []; self.btn_attach.setText("📎 Image")
        self.input.clear(); self._agent_steps = 0; self._start_stream(prov, d)

    def _start_stream(self, prov, d):
        """Open a streaming worker for the next assistant turn."""
        self._streaming_buffer = ""
        self._pending_tool_calls = []
        self.conv.add("assistant", "")    # placeholder updated as chunks arrive
        self._render_transcript()
        tools = (specs_for(prov.name, include_actions=d.llm_agent_actions)
                 if d.llm_agent_mode else None)
        self._thread = QThread()
        self._worker = StreamWorker(
            provider=prov,
            messages=self.conv.messages[:-1],   # exclude in-progress placeholder
            system=self._sys_prompt,
            model=model_for(d),
            max_tokens=d.llm_max_tokens,
            temperature=d.llm_temperature,
            tools=tools,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.tool_call.connect(self._on_tool_call)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self.btn_send.setEnabled(False); self.btn_stop.setEnabled(True)
        kind = "agent" if tools else "chat"
        self.lbl_status.setText(f"Streaming from {prov.name} ({kind})…")
        self._thread.start()

    def _compose_system_prompt(self, d) -> str | None:
        from .llm.system_prompt import app_context_prompt
        parts = [app_context_prompt()]
        if d.llm_provider == "ollama":  # small-model nudges
            parts.append("Use structured `tool_calls` field (inline "
                "`<tool_call>` text is ignored). Emit ONE tool per turn "
                "and wait for results. When citing top/bottom rows, read "
                "the data after sort/filter — don't guess by order.")
        # Memory index — names+descriptions only; recall fetches bodies.
        try:
            from .memory import MemoryStore
            idx = MemoryStore().index_text()
            if idx and "0 memories" not in idx:
                parts.append("You have a persistent memory store. Use "
                    "memory_recall(query) to fetch entries; memory_save(...) "
                    f"to record new info. Current index:\n\n{idx}")
        except Exception: pass
        if self.cb_send_context.isChecked() and self.window._current_path:
            self.window._sync_content()
            content = self.window._current_content or ""
            if len(content) > 200_000:
                content = content[:200_000] + "\n…[truncated]"
            parts.append(
                f"The user is currently viewing the file:\n"
                f"  {self.window._current_path}\n"
                f"format: {self.window._current_format}\n"
                f"--- CONTENT START ---\n{content}\n--- CONTENT END ---")
        return "\n\n".join(parts) if parts else None

    def _on_chunk(self, text: str):
        self._streaming_buffer += text
        if self.conv.messages:
            # Streaming text: keep the placeholder content in plain string form.
            self.conv.messages[-1].content = self._streaming_buffer
        self._render_transcript()

    def _on_tool_call(self, call: ToolCall):
        """Queue a tool call. We dispatch it once the stream's Done arrives,
        not in the middle, so we don't race the worker thread."""
        self._pending_tool_calls.append(call)
        # Render in-progress (collapsible) entry in the transcript
        self._render_transcript()

    def _confirm_destructive(self, call: ToolCall, tool) -> bool:
        """Ask the user before running a destructive tool, unless the
        conversation has already been trusted."""
        if getattr(self, "_conv_trusted", False):
            return True
        d = self.window.settings_manager.display
        if not d.llm_confirm_actions:
            return True
        try:
            args = json.dumps(call.arguments, indent=2)
        except (TypeError, ValueError):
            args = repr(call.arguments)
        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Allow agent action?")
        msg.setText(f"<b>{call.name}</b> wants to run.")
        msg.setInformativeText(f"Arguments:\n{args}\n\n{tool.description}")
        b_yes = msg.addButton("Allow once", QMessageBox.ButtonRole.AcceptRole)
        b_trust = msg.addButton("Trust this conversation", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is b_trust:
            self._conv_trusted = True
            return True
        return clicked is b_yes

    def _on_done(self, usage: dict, stop_reason: str):
        self.conv.add_usage(usage)
        if self._pending_tool_calls:
            self._dispatch_tools_and_continue()
            return
        self._cleanup_worker()
        u = self.conv.usage_total
        self.lbl_status.setText(
            f"Done — {usage.get('input_tokens', 0)} in / "
            f"{usage.get('output_tokens', 0)} out  ·  "
            f"total {u['input_tokens']}/{u['output_tokens']}"
        )
        # Fire scripting hook with the assistant's final text (if any).
        last = self.conv.messages[-1] if self.conv.messages else None
        if last and hasattr(self.window, "hooks") and last.role == "assistant":
            text = last.content if isinstance(last.content, str) else ""
            if text:
                self.window.hooks.fire("on_chat_response", text)

    def _dispatch_tools_and_continue(self):
        """Build the assistant block list, run the tools, append tool_results
        as a user message, then re-open the stream. Bounded by
        `llm_agent_max_steps` so a runaway agent can't loop forever."""
        d = self.window.settings_manager.display
        # Force one-tool-per-turn for ollama; tell the model what got dropped.
        dropped_names: list[str] = []
        if d.llm_provider == "ollama" and len(self._pending_tool_calls) > 1:
            dropped_names = [c.name for c in self._pending_tool_calls[1:]]
            self._pending_tool_calls = self._pending_tool_calls[:1]
            self.lbl_status.setText(f"Serialized: dropped {len(dropped_names)}")
        self._agent_steps += 1
        # Replace the placeholder text-only message with a block list.
        text = self._streaming_buffer
        blocks: list = []
        if text:
            blocks.append({"type": "text", "text": text})
        for c in self._pending_tool_calls:
            blocks.append({"type": "tool_use", "id": c.id, "name": c.name,
                           "input": c.arguments})
        self.conv.messages[-1].content = blocks

        # Execute and collect tool_result blocks. Destructive tools get a
        # one-time confirmation per conversation unless the user has opted
        # in via "Trust this conversation".
        tool_results: list = []
        for c in self._pending_tool_calls:
            tool = find_tool(c.name)
            if tool is None:
                result = f"error: unknown tool '{c.name}'"
            elif tool.destructive and not self._confirm_destructive(c, tool):
                result = "error: declined by user"
            else:
                try: result = tool.call(self.window, **(c.arguments or {}))
                except Exception as e: result = f"error: {e}"
            audit.log(c.name, c.arguments, str(result))
            if dropped_names:  # tell the model so it doesn't assume the others ran
                result = (f"[serialized: only this call ran; dropped {dropped_names}. "
                          f"Re-issue them ONE AT A TIME in later turns.]\n{result}")
                dropped_names = []
            tool_results.append({"type": "tool_result", "tool_use_id": c.id,
                                 "content": str(result)})
        self.conv.add("user", tool_results)
        self._render_transcript()

        # Cleanup the current worker; start a fresh one with the updated convo.
        prov_name = self.window.settings_manager.display.llm_provider
        self._cleanup_worker(reset_buttons=False)
        if self._agent_steps >= d.llm_agent_max_steps:
            self.lbl_status.setText(
                f"Agent step limit reached ({d.llm_agent_max_steps})."
            )
            self.btn_send.setEnabled(True); self.btn_stop.setEnabled(False)
            return
        prov = make_provider(d)
        self._start_stream(prov, d)

    def _on_error(self, kind: str, detail: str):
        if self.conv.messages and self.conv.messages[-1].role == "assistant":
            self.conv.messages[-1].content += f"\n\n*[error: {kind} — {detail}]*"
        self._render_transcript()
        self._cleanup_worker()
        self.lbl_status.setText(f"Error: {detail[:120]}")

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
        self.lbl_status.setText("Stopping…")

    def _cleanup_worker(self, reset_buttons: bool = True):
        if self._thread:
            self._thread.quit()
            self._thread.wait(500)
            self._thread = None
        self._worker = None
        if reset_buttons:
            self.btn_send.setEnabled(True); self.btn_stop.setEnabled(False)

    # -- transcript rendering -----------------------------------------------

    def _render_transcript(self):
        self.transcript.setHtml(render_transcript(
            self.conv.messages, self._pending_tool_calls,
        ))
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

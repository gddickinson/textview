"""OpenAI-compatible provider.

Works against any chat-completions endpoint that speaks the OpenAI API:
OpenAI itself, Together, Groq, Anthropic's OpenAI bridge, vLLM, Ollama's
OpenAI-compat endpoint, etc. Configure via `llm_openai_base_url`.

Function calling: tool calls arrive as `delta.tool_calls` items during
streaming. We accumulate the JSON arguments as they arrive and emit a
single `ToolCall` event per function call once the stream finishes.
"""
import json
from typing import Iterator

from .base import LLMProvider, Message, TextChunk, ToolCall, Done, Error, Event
from .credentials import get_api_key


DEFAULT_MODEL = "gpt-4o"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url or DEFAULT_BASE_URL
        self._client = None
        self._key = get_api_key("openai")

    def is_available(self) -> tuple[bool, str]:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "Install the `openai` Python package."
        if not self._key:
            return False, "No OpenAI API key configured."
        return True, ""

    def _ensure_client(self):
        if self._client is not None:
            return
        import openai  # type: ignore
        self._client = openai.OpenAI(api_key=self._key, base_url=self.base_url)

    def _to_api(self, messages: list[Message]) -> list[dict]:
        """Translate our Message format → OpenAI chat-completions schema.

        OpenAI's content blocks are slightly different from Anthropic's:
        tool calls are split between an assistant message (with
        `tool_calls`) and one or more `tool` messages bearing the result.
        """
        out: list[dict] = []
        for m in messages:
            content = m.content
            if isinstance(content, str):
                out.append({"role": m.role, "content": content})
                continue
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            tool_results: list[dict] = []
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t == "text":
                    text_parts.append(b.get("text", ""))
                elif t == "tool_use":
                    tool_calls.append({
                        "id": b.get("id"),
                        "type": "function",
                        "function": {
                            "name": b.get("name", ""),
                            "arguments": json.dumps(b.get("input", {})),
                        },
                    })
                elif t == "tool_result":
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": b.get("tool_use_id"),
                        "content": str(b.get("content", "")),
                    })
            if m.role == "assistant" and (text_parts or tool_calls):
                msg: dict = {"role": "assistant",
                             "content": "\n".join(text_parts) or None}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
            for tr in tool_results:
                out.append(tr)
        return out

    def chat_stream(
        self, messages: list[Message],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Iterator[Event]:
        ok, why = self.is_available()
        if not ok:
            yield Error(kind="config", detail=why)
            return
        try:
            self._ensure_client()
        except Exception as e:
            yield Error(kind="init", detail=str(e))
            return

        api_messages: list[dict] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        api_messages.extend(self._to_api(messages))

        kwargs_api: dict = {}
        if tools:
            kwargs_api["tools"] = tools

        try:
            stream = self._client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=api_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs_api,
            )
            tool_buf: dict[int, dict] = {}     # index → {id, name, arg_json}
            usage = {"input_tokens": 0, "output_tokens": 0,
                     "cache_read": 0, "cache_creation": 0}
            stop_reason = ""

            for chunk in stream:
                if chunk.usage:
                    usage["input_tokens"] = chunk.usage.prompt_tokens
                    usage["output_tokens"] = chunk.usage.completion_tokens
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    stop_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    yield TextChunk(text=delta.content)
                for tc in (delta.tool_calls or []):
                    slot = tool_buf.setdefault(
                        tc.index, {"id": "", "name": "", "args": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments

            for slot in tool_buf.values():
                try:
                    args = json.loads(slot["args"]) if slot["args"] else {}
                except json.JSONDecodeError:
                    args = {}
                yield ToolCall(id=slot["id"], name=slot["name"], arguments=args)
            yield Done(stop_reason=stop_reason or "end_turn", usage=usage)
        except Exception as e:
            yield Error(kind="api", detail=str(e))

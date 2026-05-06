"""Anthropic Claude provider.

Streams via `client.messages.stream(...)`. Yields TextChunk for each token
batch, then any `ToolCall` events for tool_use blocks the model emitted,
then Done with the final usage dict.
"""
from typing import Iterator

from .base import LLMProvider, Message, TextChunk, ToolCall, Done, Error, Event
from .credentials import get_api_key


DEFAULT_MODEL = "claude-opus-4-7"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self._client = None
        self._key = get_api_key("anthropic")

    def is_available(self) -> tuple[bool, str]:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "Install the `anthropic` Python package."
        if not self._key:
            return False, "No Anthropic API key configured."
        return True, ""

    def _ensure_client(self):
        if self._client is not None:
            return
        import anthropic  # type: ignore
        self._client = anthropic.Anthropic(api_key=self._key)

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

        api_messages = [{"role": m.role, "content": m.content} for m in messages
                        if m.role in ("user", "assistant")]

        kwargs_api = {}
        if tools:
            kwargs_api["tools"] = tools
        # Anthropic's Messages API accepts `system` as either a string or a
        # list of content blocks. Newer API versions sometimes reject the
        # string form ("Input should be a valid array"); the block form is
        # universally accepted, so always serialize that way.
        if system:
            kwargs_api["system"] = [{"type": "text", "text": system}]
        # `temperature` is deprecated on the extended-thinking models
        # (claude-opus-4-*, claude-sonnet-4-*). Detect by model name and
        # omit; otherwise forward the user's setting.
        m = (model or DEFAULT_MODEL).lower()
        if not (m.startswith("claude-opus-4") or m.startswith("claude-sonnet-4")
                or m.startswith("claude-haiku-4")):
            kwargs_api["temperature"] = temperature

        try:
            with self._client.messages.stream(
                model=model or DEFAULT_MODEL,
                max_tokens=max_tokens,
                messages=api_messages,
                **kwargs_api,
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        yield TextChunk(text=text)
                final = stream.get_final_message()
                # Tool-use blocks come out via the final message; emit them
                # in order so the chat panel can dispatch + continue.
                for block in getattr(final, "content", []) or []:
                    if getattr(block, "type", None) == "tool_use":
                        yield ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=dict(block.input or {}),
                        )
                yield Done(
                    stop_reason=getattr(final, "stop_reason", "") or "",
                    usage={
                        "input_tokens": getattr(final.usage, "input_tokens", 0),
                        "output_tokens": getattr(final.usage, "output_tokens", 0),
                        "cache_read": getattr(final.usage, "cache_read_input_tokens", 0) or 0,
                        "cache_creation": getattr(final.usage, "cache_creation_input_tokens", 0) or 0,
                    },
                )
        except Exception as e:
            yield Error(kind="api", detail=str(e))

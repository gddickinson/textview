"""Provider-agnostic types.

`LLMProvider.chat_stream(messages, **opts)` yields one of three event types:
    TextChunk   — arrived during streaming; append to the live message
    Done        — final usage info; conversation complete
    Error       — non-recoverable; show to the user

Tool-use events (`ToolCall`, `ToolResult`) are part of Phase 2 and not used
yet, but kept defined here so providers can already produce them.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TextChunk:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    id: str
    content: str | list


@dataclass
class Done:
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class Error:
    kind: str
    detail: str


Event = TextChunk | ToolCall | Done | Error


@dataclass
class Message:
    role: str             # "user" | "assistant" | "system"
    # Plain text or a list of API-shape blocks. Provider implementations
    # forward both forms to their endpoints unchanged. Anthropic accepts
    # both `"foo"` and `[{"type": "text", "text": "foo"}, ...]`.
    content: str | list


class LLMProvider(ABC):
    """Stream messages through a chat-completion API. Pure iterator protocol
    so the worker thread can drive UI updates synchronously."""

    name: str = "base"

    @abstractmethod
    def chat_stream(
        self, messages: list[Message],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> Iterator[Event]:
        ...

    def is_available(self) -> tuple[bool, str]:
        """Return (ok, reason). Used to disable a provider in the picker."""
        return True, ""

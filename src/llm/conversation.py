"""In-memory conversation container.

Phase 1 stays in-memory; persistence comes later. The `system_prompt`
field is rendered separately by providers (Anthropic uses a top-level
`system` parameter; Ollama prepends a system message).
"""
from dataclasses import dataclass, field

from .base import Message


@dataclass
class Conversation:
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    usage_total: dict = field(default_factory=lambda: {"input_tokens": 0,
                                                       "output_tokens": 0})

    def add(self, role: str, content):
        """Content is either a plain string OR a list of content blocks
        (e.g. for multimodal messages: [{"type": "text", ...},
        {"type": "image", "source": {...}}])."""
        self.messages.append(Message(role=role, content=content))

    def reset(self):
        self.messages.clear()
        self.usage_total = {"input_tokens": 0, "output_tokens": 0}

    def add_usage(self, usage: dict):
        for k in ("input_tokens", "output_tokens"):
            self.usage_total[k] = self.usage_total.get(k, 0) + (usage.get(k, 0) or 0)

"""Local Ollama provider.

Talks to a running Ollama daemon via `/api/chat` with `stream=true`. Each
NDJSON line on the wire becomes a TextChunk. The final line carries
`done: true` plus `prompt_eval_count` / `eval_count` which we surface as
the same usage dict shape the Anthropic provider returns.

Tool-calling support: when the caller passes `tools=[...]` (OpenAI-shape
function specs from `tools.specs_for('ollama')`), they're forwarded in
the request body. Models that support tools (qwen2.5, llama3.1+,
mistral-nemo, hermes3, …) respond with a `tool_calls` array on the
assistant message; we parse it into `ToolCall` events the agent loop in
`chat_panel` already knows how to handle.

Conversation continuation: when the agent loop sends `tool_use` /
`tool_result` blocks (Anthropic-style), we translate them into Ollama's
shape (`{"role":"assistant","tool_calls":[...]}` and
`{"role":"tool","content":"..."}`) so the model sees a coherent history.
"""
import json
import uuid
from typing import Iterator

import requests

from .base import LLMProvider, Message, TextChunk, ToolCall, Done, Error, Event


DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_URL = "http://localhost:11434"


def _translate_message(m: Message) -> list[dict]:
    """Convert one of our internal `Message`s (whose content may be a
    plain string or a list of Anthropic-shape blocks) into one or more
    Ollama-shape messages."""
    if isinstance(m.content, str):
        return [{"role": m.role, "content": m.content}]
    if not isinstance(m.content, list):
        return [{"role": m.role, "content": str(m.content)}]
    # Block-list content. Split into the Ollama equivalents.
    out: list[dict] = []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for block in m.content:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "function": {
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                }
            })
        elif btype == "tool_result":
            # Tool results become standalone messages with role="tool".
            content = block.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            out.append({"role": "tool", "content": str(content)})
    # Merge text + tool_calls into one assistant/user message if any.
    if text_parts or tool_calls:
        msg: dict = {"role": m.role, "content": "".join(text_parts)}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        # Reassemble in original order: tool_results came interleaved in
        # the block list, but for Ollama we put the assistant message
        # first then the tool messages. The agent loop in chat_panel
        # only ever produces these two combinations:
        #   assistant: [text?, tool_use*]
        #   user:      [tool_result*]
        # so this ordering is safe.
        out.insert(0, msg)
    return out


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> tuple[bool, str]:
        try:
            r = requests.get(self.base_url + "/api/tags", timeout=2)
            if r.status_code == 200:
                return True, ""
            return False, f"Ollama responded {r.status_code} at {self.base_url}"
        except requests.RequestException as e:
            return False, f"Ollama not reachable at {self.base_url} ({e.__class__.__name__})"

    def list_models(self) -> list[str]:
        try:
            r = requests.get(self.base_url + "/api/tags", timeout=2)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except requests.RequestException:
            return []

    def chat_stream(
        self, messages: list[Message],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Iterator[Event]:
        api_messages: list[dict] = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for m in messages:
            if m.role in ("user", "assistant", "system"):
                api_messages.extend(_translate_message(m))
        body: dict = {
            "model": model or DEFAULT_MODEL,
            "messages": api_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            body["tools"] = tools

        try:
            with requests.post(
                self.base_url + "/api/chat", json=body, stream=True, timeout=600,
            ) as r:
                if r.status_code != 200:
                    yield Error(kind="api",
                                detail=f"Ollama returned {r.status_code}: "
                                       f"{r.text[:200]}")
                    return
                input_tokens = output_tokens = 0
                stop_reason = "end_turn"
                emitted_tool_calls: set[str] = set()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        yield Error(kind="api", detail=obj["error"])
                        return
                    msg = obj.get("message") or {}
                    chunk = msg.get("content", "")
                    if chunk:
                        yield TextChunk(text=chunk)
                    # Tool calls usually arrive on the final chunk, but
                    # handle them on any chunk for robustness. Dedupe so
                    # we don't double-emit if Ollama repeats them.
                    for tc in (msg.get("tool_calls") or []):
                        fn = tc.get("function") or {}
                        name = fn.get("name", "")
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try: args = json.loads(args)
                            except json.JSONDecodeError: args = {"_raw": args}
                        # Synthesize an id since Ollama doesn't include one.
                        tcid = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                        sig = f"{tcid}:{name}"
                        if sig in emitted_tool_calls:
                            continue
                        emitted_tool_calls.add(sig)
                        yield ToolCall(id=tcid, name=name, arguments=args)
                    if obj.get("done"):
                        input_tokens = obj.get("prompt_eval_count", 0) or 0
                        output_tokens = obj.get("eval_count", 0) or 0
                        stop_reason = obj.get("done_reason") or "end_turn"
                        break
                yield Done(
                    stop_reason=stop_reason,
                    usage={"input_tokens": input_tokens,
                           "output_tokens": output_tokens,
                           "cache_read": 0, "cache_creation": 0},
                )
        except requests.RequestException as e:
            yield Error(kind="network", detail=str(e))

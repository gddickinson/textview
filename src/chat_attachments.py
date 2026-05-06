"""Multimodal chat input: attach images alongside the next message.

Anthropic's Messages API accepts a `content` list of blocks:

    [{"type": "text",  "text": "..."},
     {"type": "image", "source": {"type": "base64",
                                  "media_type": "image/png",
                                  "data": "<b64>"}}]

OpenAI accepts `[{"type":"text", "text":"..."}, {"type":"image_url",
"image_url":{"url":"data:image/png;base64,..."}}]`. This module produces
the Anthropic shape and exposes a translator for OpenAI.
"""
from __future__ import annotations
import base64, mimetypes
from pathlib import Path


_SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def encode_image(path: str) -> dict:
    """Read `path` and return an Anthropic-style image content block.
    Raises ValueError on unsupported extension or read failure."""
    p = Path(path)
    if p.suffix.lower() not in _SUPPORTED:
        raise ValueError(f"Unsupported image extension: {p.suffix}")
    media_type = mimetypes.guess_type(str(p))[0] or "image/png"
    try:
        data = p.read_bytes()
    except OSError as e:
        raise ValueError(f"Could not read {p}: {e}") from e
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def build_user_content(text: str, image_paths: list[str]) -> list[dict] | str:
    """Build the `content` field for a user message. Returns a plain string
    when there are no attachments (cheaper / clearer in transcripts);
    otherwise a list of content blocks (Anthropic shape)."""
    image_paths = [p for p in (image_paths or []) if p]
    if not image_paths:
        return text
    blocks: list[dict] = []
    if text:
        blocks.append({"type": "text", "text": text})
    for p in image_paths:
        blocks.append(encode_image(p))
    return blocks


def to_openai_content(content) -> list[dict] | str:
    """Translate Anthropic-shape content blocks to OpenAI's. No-op for str."""
    if isinstance(content, str): return content
    out: list[dict] = []
    for b in content:
        t = b.get("type")
        if t == "text":
            out.append({"type": "text", "text": b.get("text", "")})
        elif t == "image":
            src = b.get("source") or {}
            data = src.get("data", "")
            mt = src.get("media_type", "image/png")
            out.append({"type": "image_url",
                        "image_url": {"url": f"data:{mt};base64,{data}"}})
        else:
            out.append(b)
    return out


def transcript_html_for_content(content) -> str:
    """Render attached content blocks as HTML for the chat transcript.
    Plain text is escaped; images become inline thumbnails capped at 320px."""
    if isinstance(content, str):
        return _escape_html(content)
    chunks: list[str] = []
    for b in content:
        t = b.get("type")
        if t == "text":
            chunks.append(_escape_html(b.get("text", "")))
        elif t == "image":
            src = b.get("source") or {}
            mt = src.get("media_type", "image/png")
            data = src.get("data", "")
            chunks.append(f'<img src="data:{mt};base64,{data}" '
                          f'style="max-width:320px;max-height:320px;'
                          f'border:1px solid #888;border-radius:4px;'
                          f'margin:4px 0;" />')
    return "<br>".join(chunks)


def _escape_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<br>"))

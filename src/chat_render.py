"""Pure HTML rendering for the chat transcript.

Separated from `chat_panel.py` so the panel stays under the 500-line cap
and so the renderers are trivial to test.
"""
import html
import json

import markdown as md_lib


_STYLE = """
body{font-family:-apple-system,system-ui,sans-serif;line-height:1.5;}
.u{background:#1f2c44;color:#fff;border-radius:8px;padding:8px 12px;margin:8px 0;}
.a{background:#0f1623;color:#e6e6e6;border-radius:8px;padding:8px 12px;margin:8px 0;}
.tag{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#888;}
.tool{background:#1c2638;border-left:3px solid #88c0d0;padding:6px 10px;margin:6px 0;font-family:Menlo,monospace;font-size:12px;}
.tool .name{color:#88c0d0;}
.result{background:#1a2418;border-left:3px solid #a3be8c;padding:6px 10px;margin:6px 0;font-family:Menlo,monospace;font-size:12px;color:#cfd8c6;}
pre{background:#222;color:#eee;padding:10px;border-radius:6px;overflow-x:auto;}
code{background:#222;color:#eee;padding:2px 4px;border-radius:3px;}
"""


def md_to_html(text: str) -> str:
    if not text:
        return ""
    try:
        return md_lib.markdown(text, extensions=["extra", "fenced_code", "tables"])
    except Exception:
        return f"<pre>{html.escape(text)}</pre>"


def tool_use_block(name: str, args: dict) -> str:
    try:
        args_str = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = repr(args)
    return (f"<div class='tool'>⚙ <span class='name'>{html.escape(name)}</span>"
            f" {html.escape(args_str)}</div>")


def tool_result_block(text) -> str:
    s = str(text)
    preview = s if len(s) <= 600 else s[:600] + "\n…[truncated]"
    return (f"<div class='result'>↳ <pre style='margin:4px 0;background:transparent;color:inherit'>"
            f"{html.escape(preview)}</pre></div>")


def render_message_content(content) -> str:
    """Render a `Message.content` value (str or list of API blocks) → HTML."""
    if isinstance(content, str):
        return md_to_html(content) if content else "<i>…</i>"
    parts = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            parts.append(md_to_html(b.get("text", "")))
        elif t == "tool_use":
            parts.append(tool_use_block(b.get("name", ""), b.get("input", {})))
        elif t == "tool_result":
            parts.append(tool_result_block(b.get("content", "")))
    return "".join(parts) or "<i>…</i>"


def render_transcript(messages: list, pending_tool_calls: list) -> str:
    """Render the full chat transcript to HTML (with style header)."""
    out = [f"<style>{_STYLE}</style>"]
    if not messages:
        out.append(
            "<p style='color:#888'>Start a conversation. Choose a "
            "provider above and tap <b>API key…</b> first if you "
            "haven't set one. Toggle <b>Agent mode</b> to let "
            "Claude inspect your files via tools.</p>"
        )
    for m in messages:
        klass = "u" if m.role == "user" else "a"
        out.append(f"<div class='{klass}'><div class='tag'>{m.role.upper()}</div>")
        out.append(render_message_content(m.content))
        out.append("</div>")
    if pending_tool_calls:
        out.append("<div class='a'><div class='tag'>TOOLS PENDING</div>")
        for c in pending_tool_calls:
            out.append(tool_use_block(c.name, c.arguments))
        out.append("</div>")
    return "".join(out)

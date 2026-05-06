"""Word stats plugin — adds a Plugins → Word stats action that shows
line / word / char counts and a rough LLM token estimate for the
current buffer.

This file is intentionally short — it's the canonical example of how
a plugin uses `AppAPI`. Drop a copy in `~/.config/TextView/plugins/`
and tweak it; or write your own from scratch.
"""
from PyQt6.QtWidgets import QMessageBox


def _count(text: str) -> dict:
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    words = len(text.split())
    chars = len(text)
    # OpenAI's heuristic: ~4 chars per token for English text.
    tokens = max(0, round(chars / 4))
    return {"lines": lines, "words": words, "chars": chars, "tokens": tokens}


def register(ctx):
    api = ctx.api

    def show_stats():
        # Selection wins when there is one — that matches how spreadsheet /
        # editor users usually want stats: "what's in this highlighted
        # range?". Falls back to the whole buffer otherwise.
        sel = api.selection()
        text = sel if sel else (api.current_text() or "")
        scope = "selection" if sel else "buffer"
        c = _count(text)
        QMessageBox.information(
            ctx.window, f"Word stats ({scope})",
            f"Lines:   {c['lines']:>8}\n"
            f"Words:   {c['words']:>8}\n"
            f"Chars:   {c['chars']:>8}\n"
            f"Tokens:  {c['tokens']:>8}  (≈4 chars/token)",
        )

    action = api.add_action(
        "Word stats",
        callback=show_stats,
        menu="Plugins",
    )
    ctx.add_cleanup(lambda: api.remove_action(action))

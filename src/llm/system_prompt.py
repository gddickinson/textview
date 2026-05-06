"""System-prompt assembly for the chat panel.

Pulled out of `chat_panel.py` so the file stays under the 500-line cap
and so the prompt text is testable in isolation.
"""
from __future__ import annotations
from pathlib import Path


def _docs_dir() -> Path:
    """Project-relative `docs/` (we sit at `src/llm/`)."""
    return Path(__file__).resolve().parents[2] / "docs"


def app_context_prompt() -> str:
    """Inline `docs/overview.md` + a hint about the rest of the docs.
    The overview is short (~50 lines), so loading it inline avoids a
    tool round-trip for the common 'what does this app do' question.
    Tools (`read_doc`, `search_docs`) remain available for deeper dives."""
    docs = _docs_dir()
    try:
        overview = (docs / "overview.md").read_text(encoding="utf-8")
    except OSError:
        overview = ""
    avail = sorted(p.stem for p in docs.glob("*.md") if p.stem != "overview")
    return (
        "You're inside the TextView desktop app. The 'Overview' "
        "documentation page is included below verbatim — answer 'what "
        "does this app do' / 'how does X work' style questions directly "
        "from it, in your own words. DO NOT just list document titles "
        "back to the user — that is unhelpful. Read the relevant doc and "
        "answer the question.\n\n"
        f"For deeper detail call read_doc(name) where name ∈ "
        f"{{{', '.join(avail)}}}. For the tool reference specifically, "
        "use read_doc('agent-api').\n\n"
        f"=== docs/overview.md ===\n{overview}"
    )

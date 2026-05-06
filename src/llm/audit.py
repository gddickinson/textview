"""Audit log for LLM tool invocations.

Every tool call appends one JSON line to
`~/.local/share/TextView/llm_audit.jsonl`. The user can review what the
agent did across sessions; we can also use it for debugging weird
behavior.
"""
from datetime import datetime
import json
from pathlib import Path


_PATH = Path.home() / ".local" / "share" / "TextView" / "llm_audit.jsonl"


def log(tool: str, args: dict, result: str):
    """Append a one-line JSON record. Truncates the result preview at 1000
    chars so the log stays grep-able and doesn't blow up on huge file
    reads.
    """
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "args": args,
            "result_preview": (result or "")[:1000],
            "result_length": len(result or ""),
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # Audit logging must never break the agent.
        pass


def path() -> str:
    return str(_PATH)

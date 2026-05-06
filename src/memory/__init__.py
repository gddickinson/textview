"""TextView memory system.

File-based, LLM-agnostic memory store inspired by Claude's auto-memory.
Each record lives at `~/.config/TextView/memory/<name>.md` with YAML
frontmatter (type, description, importance, timestamps) and a free-form
markdown body. `MEMORY.md` in the same directory is the auto-generated
index — the chat panel can include it in the system prompt so any LLM
sees what's available.

Public API: `MemoryStore`, `Memory`, plus the constants
`VALID_TYPES` and `VALID_IMPORTANCE`.
"""
from .types import Memory, VALID_TYPES, VALID_IMPORTANCE
from .store import MemoryStore, MEMORY_DIR, slugify, is_valid_name

__all__ = [
    "Memory", "MemoryStore", "MEMORY_DIR",
    "VALID_TYPES", "VALID_IMPORTANCE",
    "slugify", "is_valid_name",
]

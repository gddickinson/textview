"""Memory record dataclass + enumerations.

Five types, modeled on Claude's auto-memory categories:
  - **session**    — short-term: what happened recently. Primary
    candidate for compaction.
  - **user**       — facts about the user (role, expertise, preferences).
  - **project**    — facts about ongoing work (deadlines, decisions,
    why-this-was-built-the-way-it-is).
  - **reference**  — pointers to external systems (Linear board,
    Slack channel, dashboard URL).
  - **feedback**   — corrections / guidance the user has given that
    should shape future behavior.

Three importance levels: `low` / `medium` / `high`. `high` is exempt
from auto-compaction — these are the load-bearing memories.
"""
import time
from dataclasses import dataclass, field


VALID_TYPES = {"session", "user", "project", "reference", "feedback"}
VALID_IMPORTANCE = {"low", "medium", "high"}


@dataclass
class Memory:
    name: str               # filename-safe slug, unique per store
    type: str               # one of VALID_TYPES
    description: str        # one-line summary used in the index
    content: str            # body — markdown, free-form
    importance: str = "medium"
    created: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0

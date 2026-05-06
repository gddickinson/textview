"""Shared `Tool` dataclass — separated so `tools.py` and `tools_module.py`
can both refer to it without a circular import."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    call: Callable
    destructive: bool = False

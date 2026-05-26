"""Configuration records for structural rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LowUseShortFunctionSettings:
    """Budgets for reporting short low-use functions as inline candidates."""

    enabled: bool = False
    max_call_sites: int = 2
    max_function_sloc: int = 5
    max_inline_caller_sloc: int = 50
    max_inline_caller_complexity: int = 10
    max_inline_caller_cognitive_complexity: int = 10
    max_inline_call_nesting: int = 3

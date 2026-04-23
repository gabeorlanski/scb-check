"""Fixture exercising the if-none-raise rule.

Line numbers are asserted in tests/analysis/test_if_none_raise_rule.py.
"""

from __future__ import annotations

import typer


# CASE: plain_raise / fires if-none-raise
def case_plain_raise(value):
    if value is None:
        raise ValueError("missing")
    return value


# CASE: typer_exit / negative
# Explicit CLI exits are intentional control flow.
def case_typer_exit(value):
    if value is None:
        raise typer.Exit(code=2)
    return value


# CASE: system_exit / negative
# Process exits are similarly intentional.
def case_system_exit(value):
    if value is None:
        raise SystemExit(2)
    return value

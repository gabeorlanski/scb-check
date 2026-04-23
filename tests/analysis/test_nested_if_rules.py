from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nested_if_slop.py"
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "conditionals.yaml"
)


def _hits_by_rule() -> dict[str, frozenset[int]]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")
    grouped: dict[str, set[int]] = {}
    for hit in run_sg((FIXTURE,), RULES):
        grouped.setdefault(hit.rule_id, set()).add(hit.line)
    return {rule: frozenset(lines) for rule, lines in grouped.items()}


NESTED_IF_NO_ELSE_EXPECTED = frozenset({27, 34, 142})
NESTED_GUARD_INVERT_EXPECTED = frozenset({89, 98, 106, 115, 123})


def test_nested_if_no_else_fires_only_on_strict_shape() -> None:
    hits = _hits_by_rule().get("nested-if-no-else", frozenset())
    assert hits == NESTED_IF_NO_ELSE_EXPECTED


def test_nested_guard_invert_fires_on_invertible_cases() -> None:
    hits = _hits_by_rule().get("nested-guard-invert", frozenset())
    assert hits == NESTED_GUARD_INVERT_EXPECTED


def test_rules_are_disjoint_on_this_fixture() -> None:
    """The two rules carve up the nested-if space — strict shape vs sibling
    early-exit. They should not double-fire on any line in this fixture."""
    grouped = _hits_by_rule()
    strict = grouped.get("nested-if-no-else", frozenset())
    invert = grouped.get("nested-guard-invert", frozenset())
    assert not (strict & invert)

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "dict_pattern_slop.py"
)
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "dict_patterns.yaml"
)


def _hits_by_rule() -> dict[str, frozenset[int]]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")
    grouped: dict[str, set[int]] = {}
    for hit in run_sg((FIXTURE,), RULES):
        grouped.setdefault(hit.rule_id, set()).add(hit.line)
    return {rule: frozenset(lines) for rule, lines in grouped.items()}


MANUAL_DICT_SETDEFAULT_EXPECTED = frozenset({19})
GET_THEN_NONE_CHECK_EXPECTED = frozenset({42})


def test_manual_dict_setdefault_requires_strict_equivalent_shape() -> None:
    hits = _hits_by_rule().get("manual-dict-setdefault", frozenset())
    assert hits == MANUAL_DICT_SETDEFAULT_EXPECTED


def test_get_then_none_check_requires_same_var_and_adjacent_assignment() -> (
    None
):
    hits = _hits_by_rule().get("get-then-none-check", frozenset())
    assert hits == GET_THEN_NONE_CHECK_EXPECTED

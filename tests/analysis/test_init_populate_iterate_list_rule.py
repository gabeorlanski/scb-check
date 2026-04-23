from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "init_populate_iterate_list_slop.py"
)
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "loops_and_comprehensions.yaml"
)


def _hits_for(rule_id: str) -> frozenset[int]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")
    return frozenset(
        hit.line for hit in run_sg((FIXTURE,), RULES) if hit.rule_id == rule_id
    )


def test_init_populate_iterate_list_only_fires_on_single_stmt_consumer() -> (
    None
):
    assert _hits_for("init-populate-iterate-list") == frozenset({19})

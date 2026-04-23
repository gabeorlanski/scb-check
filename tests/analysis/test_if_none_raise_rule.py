from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "if_none_raise_slop.py"
)
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "conditionals.yaml"
)


def _hits_for(rule_id: str) -> frozenset[int]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")
    return frozenset(
        hit.line for hit in run_sg((FIXTURE,), RULES) if hit.rule_id == rule_id
    )


def test_if_none_raise_excludes_explicit_exit_control_flow() -> None:
    assert _hits_for("if-none-raise") == frozenset({13})

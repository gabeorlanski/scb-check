from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "misc_class_slop.py"
)
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "misc.yaml"
)


def _hits_by_rule() -> dict[str, frozenset[int]]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")
    grouped: dict[str, set[int]] = {}
    for hit in run_sg((FIXTURE,), RULES):
        grouped.setdefault(hit.rule_id, set()).add(hit.line)
    return {rule: frozenset(lines) for rule, lines in grouped.items()}


EMPTY_EXCEPTION_EXPECTED = frozenset({14, 18, 22, 27, 31, 35})
TAGGED_UNION_EXPECTED = frozenset({65, 73, 80})


def test_empty_exception_subclass_fires_on_expected_shapes() -> None:
    hits = _hits_by_rule().get("empty-exception-subclass", frozenset())
    assert hits == EMPTY_EXCEPTION_EXPECTED


def test_dataclass_tagged_union_discriminator_fires_on_expected_shapes() -> (
    None
):
    hits = _hits_by_rule().get(
        "dataclass-tagged-union-discriminator", frozenset()
    )
    assert hits == TAGGED_UNION_EXPECTED

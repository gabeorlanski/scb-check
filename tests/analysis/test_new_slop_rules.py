"""Behavioral tests for slop rules added/extended in this change.

Each rule is asserted against `tests/fixtures/new_slop_rules.py`. Line
numbers are part of the assertion; when editing the fixture, run
`sg scan --json=stream` and update the EXPECTED mapping.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg
from scb_check.resources import combined_slop_rules_file

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "new_slop_rules.py"

NEW_RULE_EXPECTED: dict[str, frozenset[int]] = {
    "identity-wrapper-function": frozenset({24, 32}),
    "predicate-isinstance-wrapper": frozenset({58, 62}),
    "double-guard-same-value": frozenset({79}),
    "dict-from-pairs-loop": frozenset({105}),
    "redundant-blank-check": frozenset({131}),
    "mutual-isinstance-or-and": frozenset({155}),
    "suffix-slice-removesuffix": frozenset({172, 178}),
    "update-if-present-dict": frozenset({208, 210}),
    "lambda-generator-throw": frozenset({231}),
    "manual-set-union-loop": frozenset({244}),
    "fixed-chunk-file-hash": frozenset({272}),
    "oswalk-relpath-sep-replace": frozenset({297}),
    "tuple-value-err-caller-unpack": frozenset({322}),
    "optional-param-self-getter-fallback": frozenset({379}),
    "isinstance-then-bound-check": frozenset({395}),
}

MERGED_RULE_EXPECTED: dict[str, frozenset[int]] = {
    "manual-dict-counter-if-else": frozenset({344}),
    "isinstance-return-ladder": frozenset({353, 355}),
    "sorted-items-default-key": frozenset({367}),
}


@pytest.fixture(scope="module")
def hits_by_rule() -> dict[str, frozenset[int]]:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")

    with combined_slop_rules_file() as rules_path:
        raw_hits = run_sg((FIXTURE,), rules_path)

    grouped: dict[str, set[int]] = {}
    for hit in raw_hits:
        grouped.setdefault(hit.rule_id, set()).add(hit.line)
    return {rule: frozenset(lines) for rule, lines in grouped.items()}


@pytest.mark.parametrize(
    ("rule_id", "expected"),
    sorted(NEW_RULE_EXPECTED.items()),
)
def test_new_rule_fires_on_expected_lines(
    hits_by_rule: dict[str, frozenset[int]],
    rule_id: str,
    expected: frozenset[int],
) -> None:
    actual = hits_by_rule.get(rule_id, frozenset())
    assert expected.issubset(actual), (
        f"{rule_id}: expected lines {sorted(expected)} to fire, "
        f"got {sorted(actual)}"
    )


@pytest.mark.parametrize(
    ("rule_id", "expected"),
    sorted(MERGED_RULE_EXPECTED.items()),
)
def test_merged_rule_fires_on_new_shape(
    hits_by_rule: dict[str, frozenset[int]],
    rule_id: str,
    expected: frozenset[int],
) -> None:
    actual = hits_by_rule.get(rule_id, frozenset())
    assert expected.issubset(actual), (
        f"{rule_id}: merged-pattern lines {sorted(expected)} did not fire; "
        f"got {sorted(actual)}"
    )

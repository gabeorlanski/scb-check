from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scb_check.analysis.astgrep import run_sg

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = FIXTURES_DIR / "type_annotation_slop.py"
LEGACY_IMPORT_FIXTURE = FIXTURES_DIR / "legacy_typing_imports.py"
RULES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules"
    / "type_annotations.yaml"
)


def _require_sg() -> None:
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")


def _hits_by_rule(fixture: Path = FIXTURE) -> dict[str, frozenset[int]]:
    _require_sg()
    hits = run_sg((fixture,), RULES)
    grouped: dict[str, set[int]] = {}
    for hit in hits:
        grouped.setdefault(hit.rule_id, set()).add(hit.line)
    return {rule: frozenset(lines) for rule, lines in grouped.items()}


EXPECTED_HITS: dict[str, frozenset[int]] = {
    "generic-with-any": frozenset({18, 19, 20, 21, 22, 23, 24, 25, 26}),
    "union-with-any": frozenset({29, 30, 31, 32, 33}),
    "optional-any": frozenset({36, 37, 38}),
    "callable-any-return": frozenset({41, 42}),
    "object-type-annotation": frozenset({45, 46, 47}),
}

FALSE_POSITIVE_LINES = frozenset({50, 51, 52, 53, 54, 55, 56})


@pytest.mark.parametrize(
    "rule_id,expected_lines",
    sorted(EXPECTED_HITS.items()),
)
def test_rule_fires_on_expected_lines(
    rule_id: str, expected_lines: frozenset[int]
) -> None:
    grouped = _hits_by_rule()
    assert grouped.get(rule_id, frozenset()) == expected_lines


def test_no_false_positives_on_control_lines() -> None:
    grouped = _hits_by_rule()
    for rule_id, lines in grouped.items():
        if rule_id == "legacy-typing-capitalized-imports":
            continue
        offenders = lines & FALSE_POSITIVE_LINES
        assert not offenders, (
            f"{rule_id} fired on false-positive line(s) {sorted(offenders)}"
        )


def test_union_with_any_ignores_anystr_and_user_types() -> None:
    """Regression: the previous regex `Union\\[[^\\]]*Any[^\\]]*\\]` matched the
    substring "Any" inside identifiers like AnyStr or MyAnyWrapper."""
    grouped = _hits_by_rule()
    union_hits = grouped.get("union-with-any", frozenset())
    assert 50 not in union_hits  # Union[str, AnyStr]
    assert 51 not in union_hits  # Union[MyAnyWrapper, int]


def test_callable_any_param_with_concrete_return_not_flagged() -> None:
    """`Any` as an input parameter with a clarified return type is legitimate
    boundary code, not slop."""
    grouped = _hits_by_rule()
    callable_hits = grouped.get("callable-any-return", frozenset())
    assert 55 not in callable_hits  # Callable[[Any], int]


def test_pep585_lowercase_generics_covered() -> None:
    """Regression: the previous `^Dict\\[...\\]$` regex missed `dict[str, Any]`."""
    grouped = _hits_by_rule()
    generic_hits = grouped.get("generic-with-any", frozenset())
    assert 20 in generic_hits  # dict[str, Any]
    assert 21 in generic_hits  # list[Any]


def test_pep604_pipe_unions_covered() -> None:
    """Regression: the previous Union-only regex missed `str | Any` syntax."""
    grouped = _hits_by_rule()
    union_hits = grouped.get("union-with-any", frozenset())
    assert {31, 32, 33}.issubset(union_hits)


def test_optional_any_takes_precedence_over_union_with_any() -> None:
    """`Any | None` should fire optional-any only — union-with-any is a less
    specific description of the same slop."""
    grouped = _hits_by_rule()
    assert 37 in grouped.get("optional-any", frozenset())
    assert 38 in grouped.get("optional-any", frozenset())
    assert 37 not in grouped.get("union-with-any", frozenset())
    assert 38 not in grouped.get("union-with-any", frozenset())


LEGACY_IMPORT_EXPECTED = frozenset(range(8, 22))  # lines 8..21 inclusive
LEGACY_IMPORT_CONTROLS = frozenset({27, 28, 29, 30, 31, 32})


def test_legacy_typing_imports_fire_on_expected_lines() -> None:
    grouped = _hits_by_rule(LEGACY_IMPORT_FIXTURE)
    assert (
        grouped.get("legacy-typing-capitalized-imports")
        == LEGACY_IMPORT_EXPECTED
    )


def test_legacy_typing_imports_no_false_positives() -> None:
    grouped = _hits_by_rule(LEGACY_IMPORT_FIXTURE)
    hits = grouped.get("legacy-typing-capitalized-imports", frozenset())
    offenders = hits & LEGACY_IMPORT_CONTROLS
    assert not offenders, f"false positives on lines {sorted(offenders)}"


def test_legacy_typing_imports_catches_aliased_form() -> None:
    """Regression: the previous rule used `has:` without `stopBy: end`, so
    `from typing import Dict as D` (Dict nested in aliased_import) slipped through."""
    grouped = _hits_by_rule(LEGACY_IMPORT_FIXTURE)
    assert 20 in grouped.get("legacy-typing-capitalized-imports", frozenset())


def test_legacy_typing_imports_catches_union_and_set_family() -> None:
    """Regression: original regex only listed Dict/List/Optional/Tuple, omitting
    Union (even though the message advertised `X | Y`) and Set/FrozenSet/Type."""
    hits = _hits_by_rule(LEGACY_IMPORT_FIXTURE).get(
        "legacy-typing-capitalized-imports", frozenset()
    )
    assert {12, 13, 14, 15}.issubset(hits)  # Union, Set, FrozenSet, Type

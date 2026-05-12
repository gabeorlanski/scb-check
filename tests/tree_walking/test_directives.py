from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.tree_walking.directives import IgnoreDirectiveError
from scb_check.tree_walking.directives import parse_boundary_directives
from scb_check.tree_walking.directives import parse_ignore_directives


def test_ignore_directives_validate_single_rule_namespace(tmp_path: Path) -> None:
    """Source ignores accept ast-grep and structural rule IDs from one namespace."""
    source_file = tmp_path / "sample.py"
    source = dedent(
        """
        # scbc ignore[chained-dict-get,trivial-wrapper]
        def wrapper(value):
            return value
        """,
    ).strip() + "\n"

    directives = parse_ignore_directives(
        {source_file: source},
        valid_rule_ids=frozenset({"chained-dict-get", "trivial-wrapper"}),
    )

    assert tuple(directive.rule_ids for directive in directives) == (
        ("chained-dict-get", "trivial-wrapper"),
    )
    assert directives[0].target_line == 2


def test_unknown_ignore_reports_rule_namespace(tmp_path: Path) -> None:
    """Unknown source ignores name the shared rule namespace."""
    source_file = tmp_path / "sample.py"
    source = "value = 1  # scbc ignore[typo-rule]\n"

    with pytest.raises(IgnoreDirectiveError, match="unknown rule id: typo-rule"):
        parse_ignore_directives(
            {source_file: source},
            valid_rule_ids=frozenset({"trivial-wrapper"}),
        )


def test_boundary_directives_stay_separate(tmp_path: Path) -> None:
    """Boundary directives are parsed independently for ast-grep filtering."""
    source_file = tmp_path / "sample.py"
    source = dedent(
        """
        def load(raw):
            # scbc boundary: input normalization
            return raw.get("x", {})
        """,
    ).strip() + "\n"

    assert parse_boundary_directives({source_file: source})[0].directive_line == 2

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from conftest import FIXTURES

from scb_check.analysis.clones import detect_clones
from scb_check.analysis.parse import parse_file

if TYPE_CHECKING:
    from tree_sitter import Tree


def test_detect_clones_returns_instance_flags() -> None:
    source_path = FIXTURES / "corpus" / "module_a.py"
    source, tree = parse_file(source_path)

    clones = detect_clones(((source_path, source, tree),))

    assert clones
    assert all(clone.instance_count >= 2 for clone in clones)
    assert all(
        len(clone.other_instances) == clone.instance_count - 1
        for clone in clones
    )
    assert all(1 <= len(clone.first_lines) <= 3 for clone in clones)


def test_detect_clones_keeps_different_binary_operators_distinct(
    tmp_path: Path,
) -> None:
    parsed_file = _parse_source(
        tmp_path,
        """
        def add(left, right):
            result = left + right
            return result

        def subtract(left, right):
            result = left - right
            return result
        """,
    )

    clones = detect_clones((parsed_file,))

    assert clones == ()


def test_detect_clones_normalizes_identifiers_and_literals(
    tmp_path: Path,
) -> None:
    parsed_file = _parse_source(
        tmp_path,
        """
        def first(left, right):
            result = left + 1
            return result

        def second(alpha, beta):
            total = alpha + 2
            return total
        """,
    )

    clones = detect_clones((parsed_file,))

    assert len(clones) == 2
    assert {clone.instance_count for clone in clones} == {2}


def _parse_source(tmp_path: Path, source: str) -> tuple[Path, str, Tree]:
    source_path = tmp_path / "sample.py"
    source_path.write_text(
        dedent(source).strip() + "\n",
        encoding="utf-8",
    )
    parsed_source, tree = parse_file(source_path)
    return source_path, parsed_source, tree

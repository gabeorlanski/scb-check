from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from conftest import FIXTURES

from scb_check.analysis.clones import detect_clones
from scb_check.analysis.parse import parse_file

if TYPE_CHECKING:
    from tree_sitter import Tree


def test_detects_fixture_clones() -> None:
    """Fixture clone groups include counts, peers, and preview lines."""
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


def test_operator_changes_are_not_clones(
    tmp_path: Path,
) -> None:
    """Different arithmetic operators do not form structural clones."""
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


def test_normalizes_names_and_literals(
    tmp_path: Path,
) -> None:
    """Renamed variables and changed literals still form structural clones."""
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


def test_docstrings_do_not_make_short_functions_clones(
    tmp_path: Path,
) -> None:
    """Docstring lines do not count toward clone candidate size."""
    parsed_file = _parse_source(
        tmp_path,
        '''
        import math

        class Metrics:
            def cc_mass(self) -> float:
                """Return the cyclomatic complexity mass."""
                return self.cyc_complexity * math.sqrt(self.sloc)

            def cog_mass(self) -> float:
                """Return the cognitive complexity mass."""
                return self.cog_complexity * math.sqrt(self.sloc)
        ''',
    )

    clones = detect_clones((parsed_file,))

    assert clones == ()


def test_docstrings_do_not_affect_clone_hash(
    tmp_path: Path,
) -> None:
    """Docstring presence does not change a clone candidate's structure."""
    parsed_file = _parse_source(
        tmp_path,
        '''
        def first(value):
            """Explain the first function."""
            current = value + 1
            doubled = current * 2
            return doubled

        def second(value):
            current = value + 2
            doubled = current * 2
            return doubled
        ''',
    )

    clones = detect_clones((parsed_file,))

    assert len(clones) == 2
    assert {clone.instance_count for clone in clones} == {2}


def test_type_checking_imports_are_not_clones(
    tmp_path: Path,
) -> None:
    """TYPE_CHECKING import blocks are excluded from clone detection."""
    first = _parse_source(
        tmp_path,
        """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from tree_sitter import Node
            from tree_sitter import Tree
        """,
        name="first.py",
    )
    second = _parse_source(
        tmp_path,
        """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from tree_sitter import Node
            from tree_sitter import Tree
        """,
        name="second.py",
    )

    clones = detect_clones((first, second))

    assert clones == ()


def _parse_source(
    tmp_path: Path,
    source: str,
    *,
    name: str = "sample.py",
) -> tuple[Path, str, Tree]:
    source_path = tmp_path / name
    source_path.write_text(
        dedent(source).strip() + "\n",
        encoding="utf-8",
    )
    parsed_source, tree = parse_file(source_path)
    return source_path, parsed_source, tree

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from conftest import FIXTURES

from scb_check.analysis.clones import detect_clones
from scb_check.tree_walking.dispatch import ParsedFile
from scb_check.tree_walking.languages.python import PythonParser


def test_detects_fixture_clones() -> None:
    """Fixture clone groups include counts, peers, and preview lines."""
    source_path = FIXTURES / "corpus" / "module_a.py"
    parsed = PythonParser().parse(
        source_path,
        source_path.read_text(encoding="utf-8"),
    )

    clones = detect_clones((parsed,))

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
            doubled = result * 2
            return doubled

        def subtract(left, right):
            result = left - right
            doubled = result * 2
            return doubled
        """,
    )

    clones = detect_clones((parsed_file,))

    assert clones == ()


def test_two_statement_utility_body_is_clone(
    tmp_path: Path,
) -> None:
    """A repeated sanitize-then-return body is a clone candidate."""
    parsed_file = _parse_source(
        tmp_path,
        """
        def command_safe(value: str) -> str:
            safe = "".join(
                char if char.isalnum() or char in "_-" else "-"
                for char in value
            )
            return safe.strip("-_") or "item"

        def safe_path_part(value: str) -> str:
            safe = "".join(
                char if char.isalnum() or char in "._-" else "-"
                for char in value
            )
            return safe.strip(".-_") or "x"

        def get_safe_output_name(value: str) -> str:
            '''Return a filesystem-safe output name.'''
            safe = "".join(
                char if char.isalnum() or char in "_-" else "-"
                for char in value
            )
            return safe.strip("-_") or "problem"
        """,
    )

    clones = detect_clones((parsed_file,))

    assert len(clones) == 3
    assert {clone.instance_count for clone in clones} == {3}


def test_single_call_body_not_clone(
    tmp_path: Path,
) -> None:
    """A duplicated one-statement body is not a clone candidate."""
    parsed_file = _parse_source(
        tmp_path,
        """
        class GlmAgent:
            async def run(self, instruction, environment, context):
                await _run_mini_swe_agent_openai_compatible(
                    self,
                    instruction,
                    environment,
                    model_id=_normalize_glm_model_id(self.model_name),
                    env=_with_mini_swe_agent_coding_plan_env(
                        {
                            "MSWEA_CONFIGURED": "true",
                            "MSWEA_COST_TRACKING": "ignore_errors",
                        }
                    ),
                )

        class KimiAgent:
            async def run(self, instruction, environment, context):
                await _run_mini_swe_agent_openai_compatible(
                    self,
                    instruction,
                    environment,
                    model_id=_normalize_kimi_model_id(self.model_name),
                    env=_with_kimi_coding_plan_env(
                        {
                            "MSWEA_CONFIGURED": "true",
                            "MSWEA_COST_TRACKING": "ignore_errors",
                        }
                    ),
                )
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
            doubled = result * 2
            return doubled

        def second(alpha, beta):
            total = alpha + 2
            twice = total * 2
            return twice
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
) -> ParsedFile:
    source_path = tmp_path / name
    source_path.write_text(
        dedent(source).strip() + "\n",
        encoding="utf-8",
    )
    return PythonParser().parse(
        source_path,
        source_path.read_text(encoding="utf-8"),
    )

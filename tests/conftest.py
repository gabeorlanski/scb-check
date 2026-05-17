from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path

import pytest

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import FileLineSet
from scb_check.models import FindingGroups
from scb_check.models import Flags
from scb_check.models import LanguageSyntaxSummary
from scb_check.models import LineGroups
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import SymbolIR


def _make_flags(  # noqa: PLR0913
    *,
    clones: Iterable[CloneBlock] = (),
    ast_grep_hits: Iterable[AstGrepHit] = (),
    structural_findings: Iterable[RuleFinding] = (),
    high_cc_functions: Iterable[SymbolIR] = (),
    high_cog_functions: Iterable[SymbolIR] = (),
    all_functions: Iterable[SymbolIR] = (),
    syntax_by_language: Iterable[LanguageSyntaxSummary] = (),
    total_loc_by_file: Iterable[tuple[Path, int]] = (),
    clone_sloc_lines_by_file: Iterable[FileLineSet | tuple[Path, Iterable[int]]] = (),
    ast_sloc_lines_by_file: Iterable[FileLineSet | tuple[Path, Iterable[int]]] = (),
    structural_sloc_lines_by_file: Iterable[
        FileLineSet | tuple[Path, Iterable[int]]
    ] = (),
) -> Flags:
    return Flags(
        findings=FindingGroups(
            clones=tuple(clones),
            ast_grep_hits=tuple(ast_grep_hits),
            structural_findings=tuple(structural_findings),
            high_cc_functions=tuple(high_cc_functions),
            high_cog_functions=tuple(high_cog_functions),
            all_functions=tuple(all_functions),
        ),
        syntax_by_language=tuple(syntax_by_language),
        lines=LineGroups(
            total_loc_by_file=tuple(total_loc_by_file),
            clone_sloc_lines_by_file=_line_sets(clone_sloc_lines_by_file),
            ast_sloc_lines_by_file=_line_sets(ast_sloc_lines_by_file),
            structural_sloc_lines_by_file=_line_sets(structural_sloc_lines_by_file),
        ),
    )


def _line_sets(
    values: Iterable[FileLineSet | tuple[Path, Iterable[int]]],
) -> tuple[FileLineSet, ...]:
    return tuple(
        value
        if isinstance(value, FileLineSet)
        else FileLineSet.from_parts(value[0], value[1])
        for value in values
    )


@pytest.fixture
def make_flags() -> Callable[..., Flags]:
    """Return a compact builder for `Flags` test fixtures."""
    return _make_flags

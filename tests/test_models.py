from __future__ import annotations

from pathlib import Path

from scb_check.models import FileLineSet
from scb_check.models import Flags


def test_normalizes_file_line_sets() -> None:
    """Flags.from_parts normalizes file line inputs to FileLineSet tuples."""
    path = Path("sample.py")

    flags = Flags.from_parts(
        clone_sloc_lines_by_file=[(path, {1, 2})],
        ast_sloc_lines_by_file=[FileLineSet(path, frozenset({3}))],
    )

    assert flags.clone_sloc_lines_by_file == (
        FileLineSet(path, frozenset({1, 2})),
    )
    assert flags.ast_sloc_lines_by_file == (
        FileLineSet(path, frozenset({3})),
    )


def test_flags_default_empty_tuples() -> None:
    """Flags defaults every collection field to an empty tuple."""
    flags = Flags()

    assert flags.clones == ()
    assert flags.ast_grep_hits == ()
    assert flags.clone_sloc_lines_by_file == ()

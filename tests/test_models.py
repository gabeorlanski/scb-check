from __future__ import annotations

from pathlib import Path

from scb_check.models import FileLineSet
from scb_check.models import Flags


def test_flags_from_parts_normalizes_file_line_sets() -> None:
    path = Path("sample.py")

    flags = Flags.from_parts(
        clone_sloc_lines_by_file=[(path, {1, 2})],
        ast_grep_sloc_lines_by_file=[FileLineSet(path, frozenset({3}))],
    )

    assert flags.clone_sloc_lines_by_file == (
        FileLineSet(path, frozenset({1, 2})),
    )
    assert flags.ast_grep_sloc_lines_by_file == (
        FileLineSet(path, frozenset({3})),
    )


def test_flags_defaults_are_empty_tuples() -> None:
    flags = Flags()

    assert flags.clones == ()
    assert flags.ast_grep_hits == ()
    assert flags.clone_sloc_lines_by_file == ()

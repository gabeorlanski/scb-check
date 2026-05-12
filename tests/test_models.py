from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scb_check.models import FileLineSet
from scb_check.models import Flags
from scb_check.reporting.score import compute_report
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import Severity
from scb_check.tree_walking.models import SourceSpan
from scb_check.tree_walking.models import SymbolKind


def test_normalizes_file_line_sets(
    make_flags: Callable[..., Flags],
) -> None:
    """`flags` normalizes file line inputs to `FileLineSet` tuples."""
    path = Path("sample.py")

    flags = make_flags(
        clone_sloc_lines_by_file=[(path, {1, 2})],
        ast_sloc_lines_by_file=[FileLineSet(path, frozenset({3}))],
        structural_sloc_lines_by_file=[(path, {4})],
    )

    assert flags.lines.clone_sloc_lines_by_file == (
        FileLineSet(path, frozenset({1, 2})),
    )
    assert flags.lines.ast_sloc_lines_by_file == (
        FileLineSet(path, frozenset({3})),
    )
    assert flags.lines.structural_sloc_lines_by_file == (
        FileLineSet(path, frozenset({4})),
    )


def test_flags_default_empty_tuples() -> None:
    """`Flags` defaults every collection field to an empty tuple."""
    flags = Flags()

    assert flags.findings.clones == ()
    assert flags.findings.ast_grep_hits == ()
    assert flags.findings.structural_findings == ()
    assert flags.lines.clone_sloc_lines_by_file == ()
    assert flags.lines.structural_sloc_lines_by_file == ()


def test_flags_do_not_expose_flat_compat_properties() -> None:
    """Flags expose grouped findings/lines, not legacy flat shortcuts."""
    flags = Flags()

    assert "clones" not in dir(flags)
    assert "total_loc_by_file" not in dir(flags)


def test_report_does_not_expose_flat_compat_properties() -> None:
    """Reports expose grouped summaries, not legacy flat shortcuts."""
    report = compute_report(Flags())

    assert "verbosity" not in dir(report)
    assert "total_loc" not in dir(report)


def test_rule_finding_exposes_file_and_lines() -> None:
    """Structural findings expose common span shortcuts for reporting."""
    path = Path("sample.py")
    finding = RuleFinding(
        rule_id="trivial-wrapper",
        severity=Severity.WARNING,
        message="`wrapper` adds no behavior",
        span=SourceSpan(
            file=path,
            start_line=3,
            start_col=0,
            end_line=4,
            end_col=16,
        ),
        subject_name="wrapper",
        subject_qualified_name="sample.wrapper",
        subject_kind=SymbolKind.FUNCTION,
    )

    assert finding.file == path
    assert finding.start_line == 3
    assert finding.end_line == 4

from __future__ import annotations

from collections.abc import Callable
from math import isclose
from pathlib import Path

from scb_check.models import Flags
from scb_check.reporting.score import compute_report
from scb_check.tree_walking.models import SignatureIR
from scb_check.tree_walking.models import SourceSpan
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind


def test_report_unions_verbosity_lines(
    make_flags: Callable[..., Flags],
) -> None:
    """Reports union verbosity lines and computes erosion by function mass."""
    path = Path("sample.py")
    high = _function_symbol(
        path,
        name="high",
        start_line=1,
        end_line=10,
        sloc=9,
        cyc_complexity=12,
        cog_complexity=4,
    )
    low = _function_symbol(
        path,
        name="low",
        start_line=12,
        end_line=16,
        sloc=4,
        cyc_complexity=4,
        cog_complexity=12,
    )
    flags = make_flags(
        high_cc_functions=[high],
        high_cog_functions=[low],
        total_loc_by_file=[(path, 10)],
        all_functions=[high, low],
        clone_sloc_lines_by_file=[(path, {2, 3})],
        ast_sloc_lines_by_file=[(path, {3, 4})],
        structural_sloc_lines_by_file=[(path, {4, 5})],
    )

    report = compute_report(flags)

    assert report.verbosity_summary.total_loc == 10
    assert report.verbosity_summary.clone_loc == 2
    assert report.verbosity_summary.ast_grep_flagged_loc == 2
    assert report.verbosity_summary.structural_rule_loc == 2
    assert report.verbosity_summary.verbosity_flagged_loc == 4
    assert isclose(report.scores.verbosity, 0.4)
    assert report.function_summary.total_functions == 2
    assert report.function_summary.high_cc_functions == 1
    assert report.function_summary.high_cog_functions == 1
    assert isclose(report.function_summary.total_mass, 44.0)
    assert isclose(report.function_summary.high_cc_mass, 36.0)
    assert isclose(report.scores.erosion, 36.0 / 44.0)
    assert isclose(report.function_summary.total_cog_mass, 36.0)
    assert isclose(report.function_summary.high_cog_mass, 24.0)
    assert isclose(report.scores.cog_erosion, 24.0 / 36.0)


def _function_symbol(  # noqa: PLR0913
    path: Path,
    *,
    name: str,
    start_line: int,
    end_line: int,
    sloc: int,
    cyc_complexity: int,
    cog_complexity: int,
) -> SymbolIR:
    return SymbolIR(
        name=name,
        qualified_name=f"sample.{name}",
        kind=SymbolKind.FUNCTION,
        span=SourceSpan(
            file=path,
            start_line=start_line,
            start_col=0,
            end_line=end_line,
            end_col=0,
        ),
        signature=SignatureIR(),
        sloc=sloc,
        cyc_complexity=cyc_complexity,
        cog_complexity=cog_complexity,
    )

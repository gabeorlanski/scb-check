from __future__ import annotations

from math import isclose
from pathlib import Path

from scb_check.models import Flags
from scb_check.models import ParsedSymbol
from scb_check.reporting.score import compute_report


def test_report_unions_verbosity_lines() -> None:
    """Reports union verbosity lines and compute erosion by function mass."""
    path = Path("sample.py")
    high = ParsedSymbol(
        file=path,
        name="high",
        sloc=9,
        start=(1, 0),
        end=(10, 0),
        node_type="function_definition",
        statements=1,
        cyc_complexity=12,
        cog_complexity=4,
    )
    low = ParsedSymbol(
        file=path,
        name="low",
        start=(12, 0),
        end=(16, 0),
        node_type="function_definition",
        statements=1,
        sloc=4,
        cyc_complexity=4,
        cog_complexity=12,
    )
    flags = Flags.from_parts(
        high_cc_functions=[high],
        high_cog_functions=[low],
        total_loc_by_file=[(path, 10)],
        all_functions=[high, low],
        clone_sloc_lines_by_file=[(path, {2, 3})],
        ast_sloc_lines_by_file=[(path, {3, 4})],
    )

    report = compute_report(flags)

    assert report.total_loc == 10
    assert report.clone_loc == 2
    assert report.ast_grep_flagged_loc == 2
    assert report.verbosity_flagged_loc == 3
    assert isclose(report.verbosity, 0.3)
    assert report.total_functions == 2
    assert report.high_cc_functions == 1
    assert report.high_cog_functions == 1
    assert isclose(report.total_mass, 44.0)
    assert isclose(report.high_cc_mass, 36.0)
    assert isclose(report.erosion, 36.0 / 44.0)
    assert isclose(report.total_cog_mass, 36.0)
    assert isclose(report.high_cog_mass, 24.0)
    assert isclose(report.cog_erosion, 24.0 / 36.0)

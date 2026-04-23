from __future__ import annotations

from math import isclose
from pathlib import Path

from scb_check.models import Flags
from scb_check.models import FunctionSymbol
from scb_check.reporting.score import compute_report


def test_compute_report_calculates_ratios_and_masses() -> None:
    path = Path("sample.py")
    high = FunctionSymbol(
        file=path,
        name="high",
        start_line=1,
        end_line=10,
        complexity=12,
        sloc=9,
    )
    low = FunctionSymbol(
        file=path,
        name="low",
        start_line=12,
        end_line=16,
        complexity=4,
        sloc=4,
    )
    flags = Flags.from_parts(
        high_cc_functions=[high],
        total_loc_by_file=[(path, 10)],
        all_functions=[high, low],
        clone_sloc_lines_by_file=[(path, {2, 3})],
        ast_grep_sloc_lines_by_file=[(path, {3, 4})],
    )

    report = compute_report(flags)

    assert report.total_loc == 10
    assert report.clone_loc == 2
    assert report.ast_grep_flagged_loc == 2
    assert report.verbosity_flagged_loc == 3
    assert isclose(report.verbosity, 0.3)
    assert report.total_functions == 2
    assert report.high_cc_functions == 1
    assert isclose(report.total_mass, 44.0)
    assert isclose(report.high_cc_mass, 36.0)
    assert isclose(report.erosion, 36.0 / 44.0)


def test_compute_report_zero_guards() -> None:
    flags = Flags()

    report = compute_report(flags)

    assert report.verbosity == 0.0
    assert report.erosion == 0.0
    assert report.total_mass == 0.0
    assert report.high_cc_mass == 0.0

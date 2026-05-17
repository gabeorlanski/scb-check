"""Compute summary scores from analysis flags."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scb_check.models import Flags
from scb_check.models import FunctionMassSummary
from scb_check.models import Report
from scb_check.models import ReportScores
from scb_check.models import VerbositySummary
from scb_check.tree_walking.models import SymbolIR


@dataclass(frozen=True, slots=True)
class VerbosityCounts:
    """Verbosity score and source line counts."""

    verbosity: float
    flagged_loc: int
    clone_loc: int
    ast_loc: int
    structural_loc: int


@dataclass(frozen=True, slots=True)
class MassShare:
    """Mass-share score components."""

    score: float
    total: float
    flagged: float


def compute_report(flags: Flags) -> Report:
    """Compute verbosity and erosion summary metrics from `flags`."""
    total_loc = sum(loc for _, loc in flags.lines.total_loc_by_file)
    verbosity = _verbosity_counts(flags, total_loc)
    cyclomatic = _mass_share(flags.findings.all_functions, flags.findings.high_cc_functions, "cc")
    cognitive = _mass_share(flags.findings.all_functions, flags.findings.high_cog_functions, "cog")

    return Report(
        scores=ReportScores(
            verbosity=verbosity.verbosity,
            erosion=cyclomatic.score,
            cog_erosion=cognitive.score,
        ),
        verbosity_summary=VerbositySummary(
            files_scanned=len(flags.lines.total_loc_by_file),
            total_loc=total_loc,
            verbosity_flagged_loc=verbosity.flagged_loc,
            clone_loc=verbosity.clone_loc,
            ast_grep_flagged_loc=verbosity.ast_loc,
            structural_rule_loc=verbosity.structural_loc,
            structural_rule_findings=len(flags.findings.structural_findings),
        ),
        function_summary=FunctionMassSummary(
            total_functions=len(flags.findings.all_functions),
            high_cc_functions=len(flags.findings.high_cc_functions),
            high_cog_functions=len(flags.findings.high_cog_functions),
            total_mass=cyclomatic.total,
            high_cc_mass=cyclomatic.flagged,
            total_cog_mass=cognitive.total,
            high_cog_mass=cognitive.flagged,
        ),
        syntax_by_language=flags.syntax_by_language,
    )


def _verbosity_counts(flags: Flags, total_loc: int) -> VerbosityCounts:
    if not total_loc:
        return VerbosityCounts(
            verbosity=0.0,
            flagged_loc=0,
            clone_loc=0,
            ast_loc=0,
            structural_loc=0,
        )

    clone_lines_by_file = {
        entry.file: entry.lines for entry in flags.lines.clone_sloc_lines_by_file
    }
    ast_lines_by_file = {
        entry.file: entry.lines for entry in flags.lines.ast_sloc_lines_by_file
    }
    structural_lines_by_file = {
        entry.file: entry.lines for entry in flags.lines.structural_sloc_lines_by_file
    }
    flagged_loc = _count_union_lines(
        clone_lines_by_file,
        ast_lines_by_file,
        structural_lines_by_file,
    )
    return VerbosityCounts(
        verbosity=flagged_loc / total_loc,
        flagged_loc=flagged_loc,
        clone_loc=sum(len(lines) for lines in clone_lines_by_file.values()),
        ast_loc=sum(len(lines) for lines in ast_lines_by_file.values()),
        structural_loc=sum(len(lines) for lines in structural_lines_by_file.values()),
    )


def _mass_share(
    all_functions: tuple[SymbolIR, ...],
    flagged_functions: tuple[SymbolIR, ...],
    kind: str,
) -> MassShare:
    if kind == "cc":
        total = sum(symbol.cc_mass() for symbol in all_functions)
        flagged = sum(symbol.cc_mass() for symbol in flagged_functions)
    else:
        total = sum(symbol.cog_mass() for symbol in all_functions)
        flagged = sum(symbol.cog_mass() for symbol in flagged_functions)
    score = flagged / total if total else 0.0
    return MassShare(score=score, total=total, flagged=flagged)


def _count_union_lines(
    clone_lines_by_file: dict[Path, frozenset[int]],
    ast_lines_by_file: dict[Path, frozenset[int]],
    structural_lines_by_file: dict[Path, frozenset[int]],
) -> int:
    total = 0
    all_paths = (
        set(clone_lines_by_file)
        | set(ast_lines_by_file)
        | set(structural_lines_by_file)
    )
    for path in all_paths:
        clone_lines = clone_lines_by_file.get(path, frozenset())
        ast_lines = ast_lines_by_file.get(path, frozenset())
        structural_lines = structural_lines_by_file.get(path, frozenset())
        total += len(clone_lines | ast_lines | structural_lines)
    return total

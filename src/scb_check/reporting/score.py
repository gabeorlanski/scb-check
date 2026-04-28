"""Compute summary scores from analysis flags."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scb_check.models import Flags
from scb_check.models import ParsedSymbol
from scb_check.models import Report


@dataclass(frozen=True, slots=True)
class _VerbosityCounts:
    verbosity: float
    flagged_loc: int
    clone_loc: int
    ast_loc: int
    trivial_wrapper_loc: int


@dataclass(frozen=True, slots=True)
class _MassShare:
    score: float
    total: float
    flagged: float


def compute_report(flags: Flags) -> Report:
    """Compute verbosity and erosion summary metrics from `flags`."""
    total_loc = sum(loc for _, loc in flags.total_loc_by_file)
    verbosity = _verbosity_counts(flags, total_loc)
    cyclomatic = _mass_share(flags.all_functions, flags.high_cc_functions, "cc")
    cognitive = _mass_share(flags.all_functions, flags.high_cog_functions, "cog")

    return Report(
        verbosity=verbosity.verbosity,
        erosion=cyclomatic.score,
        cog_erosion=cognitive.score,
        files_scanned=len(flags.total_loc_by_file),
        total_loc=total_loc,
        verbosity_flagged_loc=verbosity.flagged_loc,
        clone_loc=verbosity.clone_loc,
        ast_grep_flagged_loc=verbosity.ast_loc,
        trivial_wrapper_loc=verbosity.trivial_wrapper_loc,
        trivial_wrappers=len(flags.trivial_wrappers),
        total_functions=len(flags.all_functions),
        high_cc_functions=len(flags.high_cc_functions),
        high_cog_functions=len(flags.high_cog_functions),
        total_mass=cyclomatic.total,
        high_cc_mass=cyclomatic.flagged,
        total_cog_mass=cognitive.total,
        high_cog_mass=cognitive.flagged,
    )


def _verbosity_counts(flags: Flags, total_loc: int) -> _VerbosityCounts:
    if not total_loc:
        return _VerbosityCounts(
            verbosity=0.0,
            flagged_loc=0,
            clone_loc=0,
            ast_loc=0,
            trivial_wrapper_loc=0,
        )

    clone_lines_by_file = {
        entry.file: entry.lines for entry in flags.clone_sloc_lines_by_file
    }
    ast_lines_by_file = {
        entry.file: entry.lines for entry in flags.ast_sloc_lines_by_file
    }
    trivial_wrapper_lines_by_file = {
        entry.file: entry.lines
        for entry in flags.trivial_wrapper_sloc_lines_by_file
    }
    flagged_loc = _count_union_lines(
        clone_lines_by_file,
        ast_lines_by_file,
        trivial_wrapper_lines_by_file,
    )
    return _VerbosityCounts(
        verbosity=flagged_loc / total_loc,
        flagged_loc=flagged_loc,
        clone_loc=sum(len(lines) for lines in clone_lines_by_file.values()),
        ast_loc=sum(len(lines) for lines in ast_lines_by_file.values()),
        trivial_wrapper_loc=sum(
            len(lines) for lines in trivial_wrapper_lines_by_file.values()
        ),
    )


def _mass_share(
    all_functions: tuple[ParsedSymbol, ...],
    flagged_functions: tuple[ParsedSymbol, ...],
    kind: str,
) -> _MassShare:
    if kind == "cc":
        total = sum(symbol.cc_mass() for symbol in all_functions)
        flagged = sum(symbol.cc_mass() for symbol in flagged_functions)
    else:
        total = sum(symbol.cog_mass() for symbol in all_functions)
        flagged = sum(symbol.cog_mass() for symbol in flagged_functions)
    score = flagged / total if total else 0.0
    return _MassShare(score=score, total=total, flagged=flagged)


def _count_union_lines(
    clone_lines_by_file: dict[Path, frozenset[int]],
    ast_lines_by_file: dict[Path, frozenset[int]],
    trivial_wrapper_lines_by_file: dict[Path, frozenset[int]],
) -> int:
    total = 0
    all_paths = (
        set(clone_lines_by_file)
        | set(ast_lines_by_file)
        | set(trivial_wrapper_lines_by_file)
    )
    for path in all_paths:
        clone_lines = clone_lines_by_file.get(path, frozenset())
        ast_lines = ast_lines_by_file.get(path, frozenset())
        trivial_wrapper_lines = trivial_wrapper_lines_by_file.get(
            path,
            frozenset(),
        )
        total += len(clone_lines | ast_lines | trivial_wrapper_lines)
    return total

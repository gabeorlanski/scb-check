from __future__ import annotations

import math
from pathlib import Path

from scb_check.models import Flags
from scb_check.models import FunctionSymbol
from scb_check.models import Report


def compute_report(flags: Flags) -> Report:
    total_loc = sum(loc for _, loc in flags.total_loc_by_file)
    clone_lines_by_file = {
        entry.file: entry.lines for entry in flags.clone_sloc_lines_by_file
    }
    ast_lines_by_file = {
        entry.file: entry.lines for entry in flags.ast_sloc_lines_by_file
    }

    clone_loc = sum(len(lines) for lines in clone_lines_by_file.values())
    ast_loc = sum(len(lines) for lines in ast_lines_by_file.values())
    verbosity_flagged_loc = _count_union_lines(
        clone_lines_by_file,
        ast_lines_by_file,
    )
    if total_loc:
        verbosity = verbosity_flagged_loc / total_loc
    else:
        verbosity = 0.0
        verbosity_flagged_loc = 0
        clone_loc = 0
        ast_loc = 0

    total_mass = sum(_mass(symbol) for symbol in flags.all_functions)
    high_cc_mass = sum(_mass(symbol) for symbol in flags.high_cc_functions)
    erosion = (high_cc_mass / total_mass) if total_mass else 0.0

    return Report(
        verbosity=verbosity,
        erosion=erosion,
        files_scanned=len(flags.total_loc_by_file),
        total_loc=total_loc,
        verbosity_flagged_loc=verbosity_flagged_loc,
        clone_loc=clone_loc,
        ast_grep_flagged_loc=ast_loc,
        total_functions=len(flags.all_functions),
        high_cc_functions=len(flags.high_cc_functions),
        total_mass=total_mass,
        high_cc_mass=high_cc_mass,
    )


def _count_union_lines(
    clone_lines_by_file: dict[Path, frozenset[int]],
    ast_lines_by_file: dict[Path, frozenset[int]],
) -> int:
    total = 0
    all_paths = set(clone_lines_by_file) | set(ast_lines_by_file)
    for path in all_paths:
        clone_lines = clone_lines_by_file.get(path, frozenset())
        ast_lines = ast_lines_by_file.get(path, frozenset())
        total += len(clone_lines | ast_lines)
    return total


def _mass(symbol: FunctionSymbol) -> float:
    if symbol.sloc <= 0:
        return 0.0
    return symbol.complexity * math.sqrt(symbol.sloc)

"""Coordinate file walking, analysis, filtering, and flag building."""

from __future__ import annotations

from collections import Counter
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.analysis.astgrep import run_sg
from scb_check.analysis.clones import detect_clones
from scb_check.analysis.ignores import BoundaryDirective
from scb_check.analysis.ignores import IgnoreDirective
from scb_check.analysis.ignores import IgnoreDirectiveError
from scb_check.analysis.ignores import parse_boundary_directives
from scb_check.analysis.ignores import parse_ignore_directives
from scb_check.analysis.loc import sloc_line_numbers
from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_file
from scb_check.analysis.symbols import extract_functions
from scb_check.config import Config
from scb_check.logging import get_logger
from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import FileLineSet
from scb_check.models import Flags
from scb_check.models import ParsedSymbol
from scb_check.resources import load_thresholds
from scb_check.resources import rules_file
from scb_check.walker import walk_python_files

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = get_logger(__name__)

__all__ = ["AnalysisResult", "IgnoreDirectiveError", "analyze", "analyze_files"]

@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Complete analysis output for CLI reporting."""

    flags: Flags
    source_lines_by_file: dict[Path, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Findings:
    clones: tuple[CloneBlock, ...]
    ast_hits: tuple[AstGrepHit, ...]
    functions: tuple[ParsedSymbol, ...]
    total_loc_by_file: tuple[tuple[Path, int], ...]
    sloc_lines_by_file: dict[Path, frozenset[int]]
    source_lines_by_file: dict[Path, tuple[str, ...]]


def analyze(
    path: Path,
    config: Config,
    *,
    include_all: bool = False,
) -> AnalysisResult:
    """Analyze Python files under `path` using `config`."""
    files = tuple(sorted(walk_python_files(path, config)))
    if not files:
        raise FileNotFoundError(f"no Python files found at {path}")
    return analyze_files(files, include_all=include_all)


def analyze_files(
    files: tuple[Path, ...],
    *,
    include_all: bool = False,
) -> AnalysisResult:
    """Analyze an explicit tuple of Python `files`."""
    findings = _collect_findings(files, include_all=include_all)
    flags = _build_flags(
        clones=findings.clones,
        ast_hits=findings.ast_hits,
        functions=findings.functions,
        total_loc_by_file=findings.total_loc_by_file,
        sloc_lines_by_file=findings.sloc_lines_by_file,
    )
    return AnalysisResult(
        flags=flags,
        source_lines_by_file=findings.source_lines_by_file,
    )


def _collect_findings(
    files: tuple[Path, ...],
    *,
    include_all: bool,
) -> Findings:
    functions: list[ParsedSymbol] = []
    total_loc_by_file: list[tuple[Path, int]] = []
    sloc_lines_by_file: dict[Path, frozenset[int]] = {}
    source_by_file: dict[Path, str] = {}
    source_lines_by_file: dict[Path, tuple[str, ...]] = {}
    parsed_files: list[tuple[Path, str, Tree]] = []

    for file_path in files:
        try:
            source, tree = parse_file(file_path)
        except ParseError as exc:
            logger.warning(
                "failed to parse file",
                file=str(file_path),
                error=str(exc),
            )
            continue

        source_by_file[file_path] = source
        source_lines_by_file[file_path] = tuple(source.splitlines())
        parsed_files.append((file_path, source, tree))
        sloc_lines = sloc_line_numbers(source, tree)
        sloc_lines_by_file[file_path] = sloc_lines
        total_loc_by_file.append((file_path, len(sloc_lines)))
        functions.extend(extract_functions(file_path, tree, sloc_lines))

    with rules_file() as rules_path:
        ast_hits = run_sg(tuple(source_lines_by_file), rules_path)
        thresholds = load_thresholds(rules_path)
        if include_all:
            filtered_ast_hits = ast_hits
        else:
            ignore_directives = parse_ignore_directives(
                source_by_file,
                rules_path,
            )
            boundary_directives = parse_boundary_directives(source_by_file)
            boundary_ranges = _boundary_function_ranges(
                boundary_directives,
                tuple(functions),
            )
            filtered_ast_hits = _filter_ignored_ast_hits(
                ast_hits,
                ignore_directives,
            )
            filtered_ast_hits = _filter_boundary_ast_hits(
                filtered_ast_hits,
                boundary_ranges,
            )
            filtered_ast_hits = _apply_count_thresholds(
                filtered_ast_hits,
                thresholds,
            )
    return Findings(
        clones=detect_clones(tuple(parsed_files)),
        ast_hits=filtered_ast_hits,
        functions=tuple(functions),
        total_loc_by_file=tuple(total_loc_by_file),
        sloc_lines_by_file=sloc_lines_by_file,
        source_lines_by_file=source_lines_by_file,
    )


def _boundary_function_ranges(
    directives: tuple[BoundaryDirective, ...],
    functions: tuple[ParsedSymbol, ...],
) -> tuple[tuple[Path, int, int], ...]:
    ranges: list[tuple[Path, int, int]] = []
    errors: list[str] = []
    for directive in directives:
        function = _containing_function(directive, functions)
        if function is None:
            errors.append(
                f"{directive.file.as_posix()}:{directive.directive_line}: "
                "scbc boundary must be inside a function body",
            )
            continue
        ranges.append((function.file, function.start_line, function.end_line))

    if errors:
        raise IgnoreDirectiveError("\n".join(errors))
    return tuple(ranges)


def _containing_function(
    directive: BoundaryDirective,
    functions: tuple[ParsedSymbol, ...],
) -> ParsedSymbol | None:
    containing = tuple(
        function
        for function in functions
        if function.file == directive.file
        and function.start_line < directive.directive_line <= function.end_line
    )
    return (
        min(containing, key=lambda function: function.end_line)
        if containing
        else None
    )


def _filter_boundary_ast_hits(
    ast_hits: tuple[AstGrepHit, ...],
    boundary_ranges: tuple[tuple[Path, int, int], ...],
) -> tuple[AstGrepHit, ...]:
    return tuple(
        hit
        for hit in ast_hits
        if not any(
            hit.file == path and start_line <= hit.line <= end_line
            for path, start_line, end_line in boundary_ranges
        )
    )


def _apply_count_thresholds(
    ast_hits: tuple[AstGrepHit, ...],
    thresholds: dict[str, int],
) -> tuple[AstGrepHit, ...]:
    if not thresholds:
        return ast_hits

    counts = Counter(
        (hit.rule_id, hit.file) for hit in ast_hits if hit.rule_id in thresholds
    )

    return tuple(
        hit
        for hit in ast_hits
        if hit.rule_id not in thresholds
        or counts[(hit.rule_id, hit.file)] >= thresholds[hit.rule_id]
    )


def _filter_ignored_ast_hits(
    ast_hits: tuple[AstGrepHit, ...],
    ignore_directives: tuple[IgnoreDirective, ...],
) -> tuple[AstGrepHit, ...]:
    ignored = {
        (directive.file, directive.target_line, rule_id)
        for directive in ignore_directives
        for rule_id in directive.rule_ids
    }
    return tuple(
        hit
        for hit in ast_hits
        if (hit.file, hit.line, hit.rule_id) not in ignored
    )


def _build_flags(
    clones: tuple[CloneBlock, ...],
    ast_hits: tuple[AstGrepHit, ...],
    functions: tuple[ParsedSymbol, ...],
    total_loc_by_file: tuple[tuple[Path, int], ...],
    sloc_lines_by_file: dict[Path, frozenset[int]],
) -> Flags:
    sorted_clones = sorted(
        clones,
        key=lambda clone: (
            clone.file.as_posix(),
            clone.start_line,
            clone.end_line,
        ),
    )
    sorted_ast_hits = sorted(
        ast_hits,
        key=lambda hit: (
            hit.file.as_posix(),
            hit.line,
            hit.col,
            hit.rule_id,
        ),
    )
    sorted_functions = sorted(
        functions,
        key=lambda symbol: (
            symbol.file.as_posix(),
            symbol.start_line,
            symbol.name,
        ),
    )
    high_cc = [symbol for symbol in sorted_functions if symbol.is_high_cc()]
    high_cog = [symbol for symbol in sorted_functions if symbol.is_high_cog()]

    clone_sloc_lines = _collect_sloc_lines(
        sorted_clones,
        sloc_lines_by_file,
        lambda clone: (clone.file, clone.start_line, clone.end_line),
    )
    ast_sloc_lines = _collect_sloc_lines(
        sorted_ast_hits,
        sloc_lines_by_file,
        lambda hit: (hit.file, hit.line, hit.end_line),
    )

    return Flags.from_parts(
        clones=sorted_clones,
        ast_grep_hits=sorted_ast_hits,
        high_cc_functions=high_cc,
        high_cog_functions=high_cog,
        total_loc_by_file=sorted(
            total_loc_by_file,
            key=lambda item: item[0].as_posix(),
        ),
        all_functions=sorted_functions,
        clone_sloc_lines_by_file=clone_sloc_lines,
        ast_sloc_lines_by_file=ast_sloc_lines,
    )


def _collect_sloc_lines[T](
    items: list[T],
    sloc_lines_by_file: dict[Path, frozenset[int]],
    span: Callable[[T], tuple[Path, int, int]],
) -> list[FileLineSet]:
    lines_by_file: defaultdict[Path, set[int]] = defaultdict(set)

    for item in items:
        path, start, end = span(item)
        sloc_lines = sloc_lines_by_file.get(path, frozenset())
        lines_by_file[path].update(
            line for line in range(start, end + 1) if line in sloc_lines
        )

    return [
        FileLineSet(path, frozenset(lines))
        for path, lines in sorted(
            lines_by_file.items(),
            key=lambda item: item[0].as_posix(),
        )
    ]

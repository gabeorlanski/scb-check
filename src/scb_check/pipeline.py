from __future__ import annotations

from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.analysis.astgrep import run_sg
from scb_check.analysis.clones import detect_clones
from scb_check.analysis.ignores import IgnoreDirective
from scb_check.analysis.ignores import IgnoreDirectiveError
from scb_check.analysis.ignores import parse_ignore_directives
from scb_check.analysis.loc import sloc_line_numbers
from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_file
from scb_check.analysis.symbols import extract_functions
from scb_check.logging import get_logger
from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import FileLineSet
from scb_check.models import Flags
from scb_check.models import FunctionSymbol
from scb_check.resources import combined_slop_rules_file
from scb_check.resources import load_min_file_count_thresholds

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = get_logger(__name__)

__all__ = ["AnalysisResult", "IgnoreDirectiveError", "analyze"]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    flags: Flags
    source_lines_by_file: dict[Path, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Findings:
    clones: tuple[CloneBlock, ...]
    ast_hits: tuple[AstGrepHit, ...]
    functions: tuple[FunctionSymbol, ...]
    total_loc_by_file: tuple[tuple[Path, int], ...]
    sloc_lines_by_file: dict[Path, frozenset[int]]
    source_lines_by_file: dict[Path, tuple[str, ...]]


def analyze(files: tuple[Path, ...]) -> AnalysisResult:
    findings = _collect_findings(files)
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


def _collect_findings(files: tuple[Path, ...]) -> Findings:
    functions: list[FunctionSymbol] = []
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
                "failed to parse file", file=str(file_path), error=str(exc)
            )
            continue

        source_by_file[file_path] = source
        source_lines_by_file[file_path] = tuple(source.splitlines())
        parsed_files.append((file_path, source, tree))
        sloc_lines = sloc_line_numbers(source, tree)
        sloc_lines_by_file[file_path] = sloc_lines
        total_loc_by_file.append((file_path, len(sloc_lines)))
        functions.extend(extract_functions(file_path, tree, sloc_lines))

    with combined_slop_rules_file() as rules_path:
        ignore_directives = parse_ignore_directives(source_by_file, rules_path)
        ast_hits = run_sg(tuple(source_lines_by_file), rules_path)
        thresholds = load_min_file_count_thresholds(rules_path)

    filtered_ast_hits = _filter_ignored_ast_hits(ast_hits, ignore_directives)
    filtered_ast_hits = _apply_count_thresholds(filtered_ast_hits, thresholds)
    return Findings(
        clones=detect_clones(tuple(parsed_files)),
        ast_hits=filtered_ast_hits,
        functions=tuple(functions),
        total_loc_by_file=tuple(total_loc_by_file),
        sloc_lines_by_file=sloc_lines_by_file,
        source_lines_by_file=source_lines_by_file,
    )


def _apply_count_thresholds(
    ast_hits: tuple[AstGrepHit, ...],
    thresholds: dict[str, int],
) -> tuple[AstGrepHit, ...]:
    if not thresholds:
        return ast_hits

    counts: dict[tuple[str, Path], int] = {}
    for hit in ast_hits:
        if hit.rule_id in thresholds:
            counts[(hit.rule_id, hit.file)] = (
                counts.get((hit.rule_id, hit.file), 0) + 1
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
    ignored_rule_counts: Counter[tuple[Path, int, str]] = Counter()
    for directive in ignore_directives:
        ignored_rule_counts.update(
            (directive.file, directive.target_line, rule_id)
            for rule_id in directive.rule_ids
        )

    filtered_hits: list[AstGrepHit] = []
    for hit in ast_hits:
        if ignored_rule_counts[(hit.file, hit.line, hit.rule_id)] > 0:
            continue
        filtered_hits.append(hit)
    return tuple(filtered_hits)


def _build_flags(
    clones: tuple[CloneBlock, ...],
    ast_hits: tuple[AstGrepHit, ...],
    functions: tuple[FunctionSymbol, ...],
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
    high_cc = [symbol for symbol in sorted_functions if symbol.complexity > 10]

    clone_sloc_lines = _collect_clone_sloc_lines(
        sorted_clones, sloc_lines_by_file
    )
    ast_sloc_lines = _collect_ast_sloc_lines(
        sorted_ast_hits, sloc_lines_by_file
    )

    return Flags.from_parts(
        clones=sorted_clones,
        ast_grep_hits=sorted_ast_hits,
        high_cc_functions=high_cc,
        total_loc_by_file=sorted(
            total_loc_by_file, key=lambda item: item[0].as_posix()
        ),
        all_functions=sorted_functions,
        clone_sloc_lines_by_file=clone_sloc_lines,
        ast_grep_sloc_lines_by_file=ast_sloc_lines,
    )


def _collect_clone_sloc_lines(
    clones: list[CloneBlock],
    sloc_lines_by_file: dict[Path, frozenset[int]],
) -> list[FileLineSet]:
    lines_by_file: defaultdict[Path, set[int]] = defaultdict(set)

    for clone in clones:
        sloc_lines = sloc_lines_by_file.get(clone.file, frozenset())
        selected = lines_by_file[clone.file]
        for line in range(clone.start_line, clone.end_line + 1):
            if line in sloc_lines:
                selected.add(line)

    return [
        FileLineSet.from_parts(path, lines)
        for path, lines in sorted(
            lines_by_file.items(), key=lambda item: item[0].as_posix()
        )
    ]


def _collect_ast_sloc_lines(
    ast_hits: list[AstGrepHit],
    sloc_lines_by_file: dict[Path, frozenset[int]],
) -> list[FileLineSet]:
    lines_by_file: defaultdict[Path, set[int]] = defaultdict(set)

    for hit in ast_hits:
        sloc_lines = sloc_lines_by_file.get(hit.file, frozenset())
        selected = lines_by_file[hit.file]
        for line in range(hit.line, hit.end_line + 1):
            if line in sloc_lines:
                selected.add(line)

    return [
        FileLineSet.from_parts(path, lines)
        for path, lines in sorted(
            lines_by_file.items(), key=lambda item: item[0].as_posix()
        )
    ]

"""Render analysis flags for human-readable CLI output."""

from __future__ import annotations

from pathlib import Path

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import SymbolIR

_RenderedFlag = tuple[tuple[str, int, int], str]


def render_flags(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    *,
    context_lines: int = 1,
    min_duplicate_lines: int | None = None,
) -> str:
    """Render `flags` with surrounding source controlled by `context_lines`."""
    rendered = [
        *_clone_entries(flags, source_lines_by_file, min_duplicate_lines),
        *_ast_grep_entries(flags, source_lines_by_file, context_lines),
        *_structural_entries(flags, source_lines_by_file, context_lines),
        *_complexity_entries(flags, source_lines_by_file, context_lines),
    ]

    if not rendered:
        return ""

    rendered.sort(key=lambda item: item[0])
    return "\n\n".join(text for _, text in rendered)


def _clone_entries(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    min_duplicate_lines: int | None,
) -> list[_RenderedFlag]:
    entries: list[_RenderedFlag] = []
    clone_sloc_lines_by_file = {
        entry.file: entry.lines for entry in flags.lines.clone_sloc_lines_by_file
    }
    for group in _group_clones(flags.findings.clones):
        anchor = group[0]
        if (
            min_duplicate_lines is not None
            and _clone_line_count(anchor, clone_sloc_lines_by_file)
            < min_duplicate_lines
        ):
            continue
        key = (_display_path(anchor.file), anchor.start_line, 0)
        text = _render_clone_group(
            group,
            source_lines_by_file,
            clone_sloc_lines_by_file,
        )
        entries.append((key, text))
    return entries


def _ast_grep_entries(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> list[_RenderedFlag]:
    entries: list[_RenderedFlag] = []
    ordered_ast_hits = dict.fromkeys(
        sorted(
            flags.findings.ast_grep_hits,
            key=lambda hit: (
                hit.file.as_posix(),
                hit.line,
                hit.col,
                hit.end_line,
                hit.end_col,
                hit.rule_id,
                hit.message,
                hit.matched_text,
            ),
        ),
    )
    for hit in ordered_ast_hits:
        key = (_display_path(hit.file), hit.line, 1)
        text = _render_ast_grep(hit, source_lines_by_file, context_lines)
        entries.append((key, text))
    return entries


def _structural_entries(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> list[_RenderedFlag]:
    entries: list[_RenderedFlag] = []
    for finding in flags.findings.structural_findings:
        key = (_display_path(finding.file), finding.start_line, 2)
        text = _render_structural_finding(
            finding,
            source_lines_by_file,
            context_lines,
        )
        entries.append((key, text))
    return entries


def _complexity_entries(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> list[_RenderedFlag]:
    entries: list[_RenderedFlag] = []
    complexity_groups = (
        (
            flags.findings.high_cc_functions,
            3,
            "erosion",
            "complexity",
            "cyc_complexity",
            "complexity > 10",
        ),
        (
            flags.findings.high_cog_functions,
            4,
            "cog_erosion",
            "cognitive complexity",
            "cog_complexity",
            "cognitive complexity > 10",
        ),
    )
    for symbols, kind_rank, title_prefix, value_label, attr_name, threshold in (
        complexity_groups
    ):
        for symbol in symbols:
            key = (_display_path(symbol.file), symbol.start_line, kind_rank)
            complexity_value = getattr(symbol, attr_name)
            text = _render_complexity_warning(
                symbol,
                source_lines_by_file,
                context_lines,
                title=(
                    f"{title_prefix}: function `{symbol.name}` "
                    f"exceeds {value_label} threshold"
                ),
                detail=(
                    f"{value_label}: {complexity_value}, "
                    f"sloc: {symbol.sloc} "
                    f"(threshold: {threshold})"
                ),
            )
            entries.append((key, text))
    return entries


def _group_clones(
    clones: tuple[CloneBlock, ...],
) -> tuple[tuple[CloneBlock, ...], ...]:
    groups: dict[str, list[CloneBlock]] = {}
    for clone in clones:  # scbc: ignore[verbose-list-append-loop]
        groups.setdefault(clone.group_hash, []).append(clone)

    return tuple(
        tuple(
            sorted(
                group,
                key=lambda clone: (_display_path(clone.file), clone.start_line),
            ),
        )
        for group in groups.values()
    )


def _render_clone_group(
    instances: tuple[CloneBlock, ...],
    source_lines_by_file: dict[Path, tuple[str, ...]],
    clone_sloc_lines_by_file: dict[Path, frozenset[int]],
) -> str:
    anchor = instances[0]
    line_count = _clone_line_count(anchor, clone_sloc_lines_by_file)
    line_number_width = max(len(str(clone.end_line)) for clone in instances)
    pad = " " * line_number_width

    lines = [
        (
            "duplicate-structure: duplicated block "
            f"({line_count} lines, {anchor.instance_count} instances)"
        ),
    ]

    for index, clone in enumerate(instances):
        lines.extend([f"{pad} ┆"] if index else [])
        lines.extend(
            [
                f"{pad} ┌─ {_display_path(clone.file)}:{clone.start_line}",
                f"{pad} │",
                *_clone_body_lines(
                    clone,
                    source_lines_by_file,
                    clone_sloc_lines_by_file,
                    line_number_width,
                ),
                f"{pad} │",
            ],
        )
    return "\n".join(lines)


def _clone_body_lines(
    clone: CloneBlock,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    clone_sloc_lines_by_file: dict[Path, frozenset[int]],
    line_number_width: int,
) -> list[str]:
    source_lines = source_lines_by_file.get(clone.file, ())
    if source_lines:
        return [
            f"{line_number:>{line_number_width}} │ "
            f"{_line_at(source_lines, line_number)}"
            for line_number in _clone_source_line_numbers(
                clone,
                source_lines,
                clone_sloc_lines_by_file,
            )
        ]
    return [
        f"{clone.start_line + offset:>{line_number_width}} │ {text}"
        for offset, text in enumerate(clone.first_lines)
    ]


def _clone_line_count(
    clone: CloneBlock,
    clone_sloc_lines_by_file: dict[Path, frozenset[int]],
) -> int:
    if clone.file not in clone_sloc_lines_by_file:
        return clone.end_line - clone.start_line + 1
    sloc_lines = clone_sloc_lines_by_file[clone.file]
    return sum(
        1 for line in sloc_lines if clone.start_line <= line <= clone.end_line
    )


def _clone_source_line_numbers(
    clone: CloneBlock,
    source_lines: tuple[str, ...],
    clone_sloc_lines_by_file: dict[Path, frozenset[int]],
) -> tuple[int, ...]:
    start_line = max(1, min(clone.start_line, len(source_lines)))
    end_line = max(start_line, min(clone.end_line, len(source_lines)))
    line_numbers = tuple(range(start_line, end_line + 1))
    if clone.file not in clone_sloc_lines_by_file:
        return line_numbers
    sloc_lines = clone_sloc_lines_by_file[clone.file]
    return tuple(line for line in line_numbers if line in sloc_lines)


def _render_ast_grep(
    hit: AstGrepHit,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> str:
    message = hit.message.strip() or "matches slop pattern"
    source_lines = source_lines_by_file.get(hit.file, ())
    rendered_lines = _source_line_range(
        source_lines,
        hit.line,
        max(hit.line, hit.end_line),
        context_lines,
    )
    fallback_lines = tuple(
        (hit.line + offset, text)
        for offset, text in enumerate(hit.matched_text.splitlines() or [hit.matched_text])
    )
    return "\n".join(
        [
            f"{hit.severity}[{hit.rule_id}]: {message}",
            *_render_source_block(
                f"{_display_path(hit.file)}:{hit.line}:{hit.col + 1}",
                source_lines,
                rendered_lines,
                fallback_lines=fallback_lines,
            ),
        ],
    )


def _render_structural_finding(
    finding: RuleFinding,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> str:
    source_lines = source_lines_by_file.get(finding.file, ())
    rendered_lines = _source_line_range(
        source_lines,
        finding.start_line,
        finding.end_line,
        context_lines,
    )
    return "\n".join(
        [
            f"{finding.rule_id}[{finding.severity.value}]: {finding.message}",
            *_render_source_block(
                f"{_display_path(finding.file)}:{finding.start_line}:{finding.span.start_col + 1}",
                source_lines,
                rendered_lines,
            ),
        ],
    )


def _render_complexity_warning(
    symbol: SymbolIR,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
    *,
    title: str,
    detail: str,
) -> str:
    source_lines = source_lines_by_file.get(symbol.file, ())
    rendered_lines = _source_line_range(
        source_lines,
        symbol.start_line,
        symbol.start_line,
        context_lines,
    )
    return "\n".join(
        [
            title,
            *_render_source_block(
                f"{_display_path(symbol.file)}:{symbol.start_line}",
                source_lines,
                rendered_lines,
                detail=detail,
            ),
        ],
    )


def _render_source_block(
    location: str,
    source_lines: tuple[str, ...],
    rendered_lines: range,
    *,
    fallback_lines: tuple[tuple[int, str], ...] = (),
    detail: str | None = None,
) -> list[str]:
    fallback_end = max((line for line, _ in fallback_lines), default=0)
    line_number_width = len(str(max(rendered_lines.stop - 1, fallback_end)))
    pad = " " * line_number_width
    lines = [f"{pad} ┌─ {location}", f"{pad} │"]
    if source_lines or not fallback_lines:
        lines.extend(
            f"{line_number:>{line_number_width}} │ "
            f"{_line_at(source_lines, line_number)}"
            for line_number in rendered_lines
        )
    else:
        lines.extend(
            f"{line_number:>{line_number_width}} │ {text}"
            for line_number, text in fallback_lines
        )

    lines.append(f"{pad} │")
    if detail is not None:
        lines.append(f"{pad} = {detail}")
    return lines


def _source_line_range(
    source_lines: tuple[str, ...],
    start_line: int,
    end_line: int,
    context_lines: int,
) -> range:
    context = max(context_lines, 0)
    first_line = max(1, start_line - context)
    last_line = max(start_line, end_line) + context
    if source_lines:
        last_line = min(last_line, len(source_lines))
    return range(first_line, last_line + 1)


def _line_at(source_lines: tuple[str, ...], line_number: int) -> str:
    if line_number <= 0 or line_number > len(source_lines):
        return ""
    return source_lines[line_number - 1]


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()

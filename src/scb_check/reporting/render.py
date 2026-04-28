"""Render analysis flags for human-readable CLI output."""

from __future__ import annotations

from pathlib import Path

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.models import ParsedSymbol


def render_flags(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    *,
    context_lines: int = 1,
) -> str:
    """Render `flags` with surrounding source controlled by `context_lines`."""
    rendered: list[tuple[tuple[str, int, int], str]] = []
    clone_sloc_lines_by_file = {
        entry.file: entry.lines for entry in flags.clone_sloc_lines_by_file
    }

    for group in _group_clones(flags.clones):
        anchor = group[0]
        key = (_display_path(anchor.file), anchor.start_line, 0)
        rendered.append(
            (
                key,
                _render_clone_group(
                    group,
                    source_lines_by_file,
                    clone_sloc_lines_by_file,
                ),
            ),
        )

    for hit in _ordered_ast_grep_hits(flags.ast_grep_hits):
        key = (_display_path(hit.file), hit.line, 1)
        rendered.append(
            (
                key,
                _render_ast_grep(
                    hit,
                    source_lines_by_file,
                    context_lines,
                ),
            ),
        )

    for symbols, kind_rank, renderer in (
        (flags.high_cc_functions, 2, _render_erosion),
        (flags.high_cog_functions, 3, _render_cog_erosion),
    ):
        for symbol in symbols:
            key = (_display_path(symbol.file), symbol.start_line, kind_rank)
            rendered.append(
                (
                    key,
                    renderer(
                        symbol,
                        source_lines_by_file,
                        context_lines,
                    ),
                ),
            )

    if not rendered:
        return ""

    rendered.sort(key=lambda item: item[0])
    return "\n\n".join(text for _, text in rendered)


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


def _make_clone_body_lines(
    clone: CloneBlock,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    clone_sloc_lines_by_file: dict[Path, frozenset[int]],
    line_number_width: int,
    pad: str,
) -> list[str]:
    return [
        f"{pad} ┌─ {_display_path(clone.file)}:{clone.start_line}",
        f"{pad} │",
        *_clone_body_lines(
            clone,
            source_lines_by_file,
            clone_sloc_lines_by_file,
            line_number_width,
        ),
        f"{pad} │",
    ]


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
        lines.extend(
            ([f"{pad} ┆"] if index else [])
            + _make_clone_body_lines(
                clone,
                source_lines_by_file,
                clone_sloc_lines_by_file,
                line_number_width,
                pad,
            ),
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
    first_col = hit.col + 1
    message = hit.message.strip() or "matches slop pattern"

    start_line = hit.line
    end_line = max(hit.line, hit.end_line)
    source_lines = source_lines_by_file.get(hit.file, ())
    rendered_lines = _source_line_range(
        source_lines,
        start_line,
        end_line,
        context_lines,
    )
    line_number_width = len(str(max(rendered_lines.stop - 1, end_line)))

    lines = [
        f"warning[{hit.rule_id}]: {message}",
        f"{' ' * line_number_width} ┌─ {_display_path(hit.file)}:{hit.line}:{first_col}",
        f"{' ' * line_number_width} │",
    ]
    if source_lines:
        lines.extend(
            f"{line_number:>{line_number_width}} │ "
            f"{_line_at(source_lines, line_number)}"
            for line_number in rendered_lines
        )
    else:
        matched_lines = hit.matched_text.splitlines() or [hit.matched_text]
        for offset, text in enumerate(matched_lines):
            line_number = start_line + offset
            lines.append(f"{line_number:>{line_number_width}} │ {text}")

    lines.append(f"{' ' * line_number_width} │")
    return "\n".join(lines)


def _ordered_ast_grep_hits(
    ast_hits: tuple[AstGrepHit, ...],
) -> tuple[AstGrepHit, ...]:
    return tuple(
        dict.fromkeys(
            sorted(
                ast_hits,
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
        ),
    )


def _render_erosion(
    symbol: ParsedSymbol,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> str:
    return _render_complexity_warning(
        symbol,
        source_lines_by_file,
        context_lines,
        title=(
            f"erosion: function `{symbol.name}` "
            "exceeds complexity threshold"
        ),
        detail=(
            f"complexity: {symbol.cyc_complexity}, sloc: {symbol.sloc} "
            "(threshold: complexity > 10)"
        ),
    )


def _render_cog_erosion(
    symbol: ParsedSymbol,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    context_lines: int,
) -> str:
    return _render_complexity_warning(
        symbol,
        source_lines_by_file,
        context_lines,
        title=(
            f"cog_erosion: function `{symbol.name}` "
            "exceeds cognitive complexity threshold"
        ),
        detail=(
            f"cognitive complexity: {symbol.cog_complexity}, "
            f"sloc: {symbol.sloc} "
            "(threshold: cognitive complexity > 10)"
        ),
    )


def _render_complexity_warning(
    symbol: ParsedSymbol,
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
    line_number_width = len(
        str(max(rendered_lines.stop - 1, symbol.start_line))
    )

    lines = [
        title,
        f"{' ' * line_number_width} ┌─ {_display_path(symbol.file)}:{symbol.start_line}",
        f"{' ' * line_number_width} │",
    ]
    lines.extend(
        f"{line_number:>{line_number_width}} │ "
        f"{_line_at(source_lines, line_number)}"
        for line_number in rendered_lines
    )
    lines.extend(
        [
            f"{' ' * line_number_width} │",
            f"{' ' * line_number_width} = {detail}",
        ],
    )
    return "\n".join(lines)


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

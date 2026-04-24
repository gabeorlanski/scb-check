from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.models import FunctionSymbol


def render_flags(
    flags: Flags,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    *,
    context_lines: int = 1,
    verbosity: int = 0,
) -> str:
    """Render ``flags`` as human-readable ty/ruff-style warning blocks.

    Blocks are ordered by ``(display_path, start_line, kind_rank)`` with
    kind_rank clone=0, ast-grep=1, erosion=2, and separated by blank
    lines. Each block starts with a stable textual prefix
    (``duplicate-structure:``, ``warning[<rule>]:``, ``erosion:``) that
    tests assert on. Clones are grouped by ``group_hash`` so every
    duplicate of a block renders once with all instances inline.
    Returns the empty string when ``flags`` has nothing to report.
    """

    rendered: list[tuple[tuple[str, int, int], str]] = []

    for group in _group_clones(flags.clones):
        anchor = group[0]
        key = (_display_path(anchor.file), anchor.start_line, 0)
        rendered.append(
            (
                key,
                _render_clone_group(
                    group,
                    source_lines_by_file,
                ),
            )
        )

    for hit in _ordered_ast_grep_hits(flags.ast_grep_hits):
        key = (_display_path(hit.file), hit.line, 1)
        rendered.append(
            (
                key,
                _render_ast_grep(
                    hit,
                    source_lines_by_file,
                ),
            )
        )

    for symbol in flags.high_cc_functions:
        key = (_display_path(symbol.file), symbol.start_line, 2)
        rendered.append(
            (
                key,
                _render_erosion(
                    symbol,
                    source_lines_by_file,
                ),
            )
        )

    if not rendered:
        return ""

    rendered.sort(key=lambda item: item[0])
    return "\n\n".join(text for _, text in rendered)


def _group_clones(
    clones: tuple[CloneBlock, ...],
) -> list[tuple[CloneBlock, ...]]:
    groups: dict[str, list[CloneBlock]] = defaultdict(list)
    order: list[str] = []

    for clone in clones:  # scbc: ignore[verbose-list-append-loop]
        if clone.group_hash not in groups:
            order.append(clone.group_hash)
        groups[clone.group_hash].append(clone)

    ordered: list[tuple[CloneBlock, ...]] = []
    for hash_value in order:
        sorted_instances = sorted(
            groups[hash_value],
            key=lambda clone: (_display_path(clone.file), clone.start_line),
        )
        ordered.append(tuple(sorted_instances))
    return ordered


def _make_clone_body_lines(
    clone: CloneBlock,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    line_number_width: int,
    pad: str,
) -> list[str]:
    return [
        f"{pad} ┌─ {_display_path(clone.file)}:{clone.start_line}",
        f"{pad} │",
        *_clone_body_lines(clone, source_lines_by_file, line_number_width),
        f"{pad} │",
    ]


def _render_clone_group(
    instances: tuple[CloneBlock, ...],
    source_lines_by_file: dict[Path, tuple[str, ...]],
) -> str:
    anchor = instances[0]
    line_count = anchor.end_line - anchor.start_line + 1
    line_number_width = max(len(str(clone.end_line)) for clone in instances)
    pad = " " * line_number_width

    lines = [
        (
            "duplicate-structure: duplicated block "
            f"({line_count} lines, {anchor.instance_count} instances)"
        )
    ]

    for index, clone in enumerate(instances):
        if index > 0:
            lines.append(f"{pad} ┆")
        lines.extend(
            _make_clone_body_lines(
                clone,
                source_lines_by_file,
                line_number_width,
                pad,
            )
        )
    return "\n".join(lines)


def _clone_body_lines(
    clone: CloneBlock,
    source_lines_by_file: dict[Path, tuple[str, ...]],
    line_number_width: int,
) -> list[str]:
    source_lines = source_lines_by_file.get(clone.file, ())
    if source_lines:
        start_line = max(1, min(clone.start_line, len(source_lines)))
        end_line = max(start_line, min(clone.end_line, len(source_lines)))
        return [
            f"{line_number:>{line_number_width}} │ "
            f"{_line_at(source_lines, line_number)}"
            for line_number in range(start_line, end_line + 1)
        ]
    return [
        f"{clone.start_line + offset:>{line_number_width}} │ {text}"
        for offset, text in enumerate(clone.first_lines)
    ]


def _render_ast_grep(
    hit: AstGrepHit,
    source_lines_by_file: dict[Path, tuple[str, ...]],
) -> str:
    first_col = hit.col + 1
    message = hit.message.strip() or "matches slop pattern"

    start_line = hit.line
    end_line = max(hit.line, hit.end_line)
    line_number_width = len(str(max(start_line, end_line)))
    source_lines = source_lines_by_file.get(hit.file, ())

    lines = [
        f"warning[{hit.rule_id}]: {message}",
        f"{' ' * line_number_width} ┌─ {_display_path(hit.file)}:{hit.line}:{first_col}",
        f"{' ' * line_number_width} │",
    ]
    if source_lines:
        lines.extend(
            f"{line_number:>{line_number_width}} │ "
            f"{_line_at(source_lines, line_number)}"
            for line_number in range(start_line, end_line + 1)
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
    sorted_hits = tuple(
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
        )
    )
    return _dedupe_hits(sorted_hits)


def _dedupe_hits(hits: tuple[AstGrepHit, ...]) -> tuple[AstGrepHit, ...]:
    seen: set[tuple[str, int, int, int, int, str, str, str]] = set()
    deduped: list[AstGrepHit] = []

    for hit in hits:
        dedupe_key = (
            hit.file.as_posix(),
            hit.line,
            hit.end_line,
            hit.col,
            hit.end_col,
            hit.rule_id,
            hit.matched_text,
            hit.message,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(hit)

    return tuple(deduped)


def _render_erosion(
    symbol: FunctionSymbol,
    source_lines_by_file: dict[Path, tuple[str, ...]],
) -> str:
    source_lines = source_lines_by_file.get(symbol.file, ())
    definition_line = _line_at(source_lines, symbol.start_line)
    line_number_width = len(str(symbol.start_line))

    lines = [
        f"erosion: function `{symbol.name}` exceeds complexity threshold",
        f"{' ' * line_number_width} ┌─ {_display_path(symbol.file)}:{symbol.start_line}",
        f"{' ' * line_number_width} │",
        f"{symbol.start_line:>{line_number_width}} │ {definition_line}",
        f"{' ' * line_number_width} │",
        (
            f"{' ' * line_number_width} = "
            f"complexity: {symbol.complexity}, sloc: {symbol.sloc} "
            "(threshold: complexity > 10)"
        ),
    ]
    return "\n".join(lines)


def _line_at(source_lines: tuple[str, ...], line_number: int) -> str:
    if line_number <= 0 or line_number > len(source_lines):
        return ""
    return source_lines[line_number - 1]


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()

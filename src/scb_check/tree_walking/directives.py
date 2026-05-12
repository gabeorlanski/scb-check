"""Parse `scbc` source directives from comment tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from token import COMMENT
from token import DEDENT
from token import ENDMARKER
from token import INDENT
from token import NEWLINE
from token import NL
from tokenize import TokenError
from tokenize import TokenInfo
from tokenize import generate_tokens
from typing import NamedTuple

import yaml

from scb_check.resources import load_rule_ids

_IGNORE_DIRECTIVE_RE = re.compile(
    r"^scbc\s+ignore\[(?P<rule_ids>[^\]]*)\].*$",
)
_BOUNDARY_DIRECTIVE_RE = re.compile(r"^scbc\s+boundary(?:[:\s].*)?$")
_NON_CODE_TOKEN_TYPES = frozenset(
    {
        COMMENT,
        DEDENT,
        ENDMARKER,
        INDENT,
        NEWLINE,
        NL,
    },
)
_TOKEN_ERROR_LOCATION_ARG = 2


@dataclass(frozen=True, slots=True)
class IgnoreDirective:
    """A source comment that suppresses rule findings on target code."""

    file: Path
    directive_line: int
    target_line: int
    rule_ids: tuple[str, ...]


class IgnoreDirectiveError(ValueError):  # scbc ignore[empty-exception-subclass] Boundary error type consumed by CLI.
    """Raised when source directives are malformed or invalid."""


class BoundaryDirective(NamedTuple):
    """A source comment that suppresses ast-grep findings in a function."""

    file: Path
    directive_line: int


@dataclass(frozen=True, slots=True)
class DirectiveScan:
    """Token scan result for `scbc` source directives."""

    comments_by_line: dict[int, tuple[str, bool]]
    code_lines: set[int]
    ignore_matches: tuple[tuple[int, str], ...]
    boundary_lines: tuple[int, ...]


def parse_ignore_directives(
    source_by_file: dict[Path, str],
    *,
    valid_rule_ids: frozenset[str],
) -> tuple[IgnoreDirective, ...]:
    """Return validated `scbc ignore[...]` directives from source files."""
    directives: list[IgnoreDirective] = []
    errors: list[str] = []
    for file_path, source in sorted(
        source_by_file.items(), key=lambda item: item[0].as_posix(),
    ):
        file_directives, file_errors = _parse_file_directives(
            file_path,
            source,
            valid_rule_ids,
        )
        directives.extend(file_directives)
        errors.extend(file_errors)

    if errors:
        raise IgnoreDirectiveError("\n".join(errors))
    return tuple(directives)


def parse_boundary_directives(
    source_by_file: dict[Path, str],
) -> tuple[BoundaryDirective, ...]:
    """Return `scbc boundary` directives from source files."""
    directives: list[BoundaryDirective] = []
    errors: list[str] = []
    for file_path, source in sorted(
        source_by_file.items(), key=lambda item: item[0].as_posix(),
    ):
        try:
            scan = _scan_directives(source)
        except TokenError as exc:
            errors.append(
                (
                    f"{file_path.as_posix()}:{_token_error_line(exc)}: "
                    f"failed to parse boundary directives: {exc}"
                ),
            )
            continue

        directives.extend(
            BoundaryDirective(file=file_path, directive_line=directive_line)
            for directive_line in scan.boundary_lines
        )

    if errors:
        raise IgnoreDirectiveError("\n".join(errors))
    return tuple(directives)


def load_ast_grep_rule_ids(rules_path: Path) -> frozenset[str]:
    """Load rule IDs from an ast-grep YAML rule file."""
    try:
        rule_ids = load_rule_ids(rules_path)
    except (OSError, yaml.YAMLError) as exc:
        raise IgnoreDirectiveError(
            f"failed to load ast-grep rules: {exc}",
        ) from exc

    if not rule_ids:
        raise IgnoreDirectiveError(
            f"failed to load ast-grep rules: no rule ids found in {rules_path}",
        )
    return rule_ids


def _parse_file_directives(
    file_path: Path,
    source: str,
    valid_rule_ids: frozenset[str],
) -> tuple[tuple[IgnoreDirective, ...], tuple[str, ...]]:
    try:
        scan = _scan_directives(source)
    except TokenError as exc:
        return (), (
            (
                f"{file_path.as_posix()}:{_token_error_line(exc)}: "
                f"failed to parse ignore directives: {exc}"
            ),
        )

    directives: list[IgnoreDirective] = []
    errors: list[str] = []
    for directive_line, directive in scan.ignore_matches:
        rule_ids, rule_errors = _validated_rule_ids(
            file_path,
            directive_line,
            directive,
            valid_rule_ids,
        )
        if rule_errors:
            errors.extend(rule_errors)
        target_line = _get_target_line(
            directive_line,
            scan.comments_by_line,
            scan.code_lines,
        )
        if target_line is None:
            errors.append(
                f"{file_path.as_posix()}:{directive_line}: "
                "scbc ignore has no target code line",
            )

        if rule_errors or target_line is None:
            continue

        directives.append(
            IgnoreDirective(
                file=file_path,
                directive_line=directive_line,
                target_line=target_line,
                rule_ids=rule_ids,
            ),
        )

    return tuple(directives), tuple(errors)


def _scan_directives(source: str) -> DirectiveScan:
    comments: dict[int, tuple[str, bool]] = {}
    code_lines: set[int] = set()
    ignore_matches: list[tuple[int, str]] = []
    boundary_lines: list[int] = []

    for token in generate_tokens(iter(source.splitlines(keepends=True)).__next__):
        _scan_token(token, comments, code_lines, ignore_matches, boundary_lines)

    return DirectiveScan(
        comments_by_line=comments,
        code_lines=code_lines,
        ignore_matches=tuple(ignore_matches),
        boundary_lines=tuple(boundary_lines),
    )


def _scan_token(
    token: TokenInfo,
    comments: dict[int, tuple[str, bool]],
    code_lines: set[int],
    ignore_matches: list[tuple[int, str]],
    boundary_lines: list[int],
) -> None:
    if token.type != COMMENT:
        if token.type not in _NON_CODE_TOKEN_TYPES:
            code_lines.add(token.start[0])
        return

    comment_text = token.string.removeprefix("#").strip()
    comments[token.start[0]] = (
        comment_text,
        token.line[: token.start[1]].strip() != "",
    )
    ignore_directive = _match_ignore_directive(comment_text)
    if ignore_directive is not None:
        ignore_matches.append((token.start[0], ignore_directive))
        return
    if _BOUNDARY_DIRECTIVE_RE.match(comment_text):
        boundary_lines.append(token.start[0])


def _match_ignore_directive(comment_text: str) -> str | None:
    match = _IGNORE_DIRECTIVE_RE.match(comment_text)
    return match.group("rule_ids") if match else None


def _validated_rule_ids(
    file_path: Path,
    line_no: int,
    raw_rule_ids: str,
    valid_rule_ids: frozenset[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    parsed_rule_ids = tuple(
        dict.fromkeys(
            rule_id.strip()
            for rule_id in raw_rule_ids.split(",")
            if rule_id.strip()
        ),
    )
    if not parsed_rule_ids:
        return (), (
            f"{file_path.as_posix()}:{line_no}: "
            "scbc ignore requires at least one rule id",
        )

    errors = tuple(
        error
        for rule_id in parsed_rule_ids
        if (
            error := _rule_id_error(
                file_path,
                line_no,
                rule_id,
                valid_rule_ids,
            )
        )
        is not None
    )
    return parsed_rule_ids, errors


def _rule_id_error(
    file_path: Path,
    line_no: int,
    rule_id: str,
    valid_rule_ids: frozenset[str],
) -> str | None:
    message = None
    if rule_id == "*":
        message = "wildcard ignores are not supported"
    elif rule_id not in valid_rule_ids:
        message = f"unknown rule id: {rule_id}"

    return (
        f"{file_path.as_posix()}:{line_no}: {message}"
        if message is not None
        else None
    )


def _get_target_line(
    directive_line: int,
    comments_by_line: dict[int, tuple[str, bool]],
    code_lines: set[int],
) -> int | None:
    _, has_code_prefix = comments_by_line[directive_line]
    if has_code_prefix:
        return directive_line

    return min(
        (line_no for line_no in code_lines if line_no > directive_line),
        default=None,
    )


def _token_error_line(exc: TokenError) -> int:
    if len(exc.args) >= _TOKEN_ERROR_LOCATION_ARG and isinstance(exc.args[1], tuple):
        line_no = exc.args[1][0]
        if isinstance(line_no, int):
            return line_no
    return 1

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
from tokenize import generate_tokens

import yaml

COMMENT_DIRECTIVE_PATTERN = re.compile(
    r"^scbc\s+ignore\[(?P<rule_ids>[^\]]*)\].*$"
)
NON_CODE_TOKEN_TYPES = frozenset(
    {
        COMMENT,
        DEDENT,
        ENDMARKER,
        INDENT,
        NEWLINE,
        NL,
    }
)


@dataclass(frozen=True, slots=True)
class IgnoreDirective:
    file: Path
    directive_line: int
    target_line: int
    rule_ids: tuple[str, ...]


class IgnoreDirectiveError(ValueError):
    pass


def parse_ignore_directives(
    source_by_file: dict[Path, str],
    rules_path: Path,
) -> tuple[IgnoreDirective, ...]:
    valid_rule_ids = _load_valid_rule_ids(rules_path)

    directives: list[IgnoreDirective] = []
    errors: list[str] = []
    for file_path, source in sorted(
        source_by_file.items(), key=lambda item: item[0].as_posix()
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


def _load_valid_rule_ids(rules_path: Path) -> frozenset[str]:
    try:
        with rules_path.open("r", encoding="utf-8") as rules_file:
            documents = tuple(yaml.safe_load_all(rules_file))
    except (OSError, yaml.YAMLError) as exc:
        raise IgnoreDirectiveError(
            f"failed to load ast-grep rules: {exc}"
        ) from exc

    rule_ids: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            continue
        rule_id = document.get("id")
        if isinstance(rule_id, str):
            rule_ids.add(rule_id)

    if not rule_ids:
        raise IgnoreDirectiveError(
            f"failed to load ast-grep rules: no rule ids found in {rules_path}"
        )
    return frozenset(rule_ids)


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


def _parse_file_directives(
    file_path: Path,
    source: str,
    valid_rule_ids: frozenset[str],
) -> tuple[tuple[IgnoreDirective, ...], tuple[str, ...]]:
    comments_by_line: dict[int, tuple[str, bool]] = {}
    code_lines: set[int] = set()
    matched_directives: list[tuple[int, str]] = []
    errors: list[str] = []

    token_lines = source.splitlines(keepends=True)
    try:
        tokens = tuple(generate_tokens(iter(token_lines).__next__))
    except TokenError as exc:
        line_no = _token_error_line(exc)
        errors.append(
            _format_error(
                file_path,
                line_no,
                f"failed to parse ignore directives: {exc}",
            )
        )
        return (), tuple(errors)

    for token in tokens:
        if token.type == COMMENT:
            comment_text = token.string.removeprefix("#").strip()
            has_code_prefix = bool(token.line[: token.start[1]].strip())
            comments_by_line[token.start[0]] = (comment_text, has_code_prefix)
            directive = _match_directive(comment_text)
            if directive is not None:
                matched_directives.append((token.start[0], directive))
            continue

        if token.type not in NON_CODE_TOKEN_TYPES:
            code_lines.add(token.start[0])

    directives: list[IgnoreDirective] = []
    for directive_line, directive in matched_directives:
        rule_ids_text = directive
        rule_ids, rule_errors = _validated_rule_ids(
            file_path,
            directive_line,
            rule_ids_text,
            valid_rule_ids,
        )
        if rule_errors:
            errors.extend(rule_errors)
        target_line = _get_target_line(
            directive_line,
            comments_by_line,
            code_lines,
        )
        if target_line is None:
            errors.append(
                _format_error(
                    file_path,
                    directive_line,
                    "scbc ignore has no target code line",
                )
            )

        if rule_errors or target_line is None:
            continue

        directives.append(
            IgnoreDirective(
                file=file_path,
                directive_line=directive_line,
                target_line=target_line,
                rule_ids=rule_ids,
            )
        )

    return tuple(directives), tuple(errors)


def _match_directive(comment_text: str) -> str | None:
    match = COMMENT_DIRECTIVE_PATTERN.match(comment_text)
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
        )
    )
    if not parsed_rule_ids:
        return (), (
            _format_error(
                file_path,
                line_no,
                "scbc ignore requires at least one rule id",
            ),
        )

    errors: list[str] = []
    for rule_id in parsed_rule_ids:
        if rule_id == "*":
            errors.append(
                _format_error(
                    file_path,
                    line_no,
                    "wildcard ignores are not supported",
                )
            )
            continue
        if rule_id not in valid_rule_ids:
            errors.append(
                _format_error(
                    file_path,
                    line_no,
                    f"unknown ast-grep rule id: {rule_id}",
                )
            )
    return parsed_rule_ids, tuple(errors)


def _token_error_line(exc: TokenError) -> int:
    if len(exc.args) >= 2 and isinstance(exc.args[1], tuple):
        line_no = exc.args[1][0]
        if isinstance(line_no, int):
            return line_no
    return 1


def _format_error(file_path: Path, line_no: int, message: str) -> str:
    return f"{file_path.as_posix()}:{line_no}: {message}"

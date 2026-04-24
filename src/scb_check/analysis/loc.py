"""Count source lines of code for Python files."""

from __future__ import annotations

from token import COMMENT
from token import DEDENT
from token import ENDMARKER
from token import INDENT
from token import NEWLINE
from token import NL
from tokenize import generate_tokens
from typing import TYPE_CHECKING

from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_source

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

IGNORED_SLOC_TOKEN_TYPES = {
    COMMENT,
    DEDENT,
    ENDMARKER,
    INDENT,
    NEWLINE,
    NL,
}


def sloc_line_numbers(
    source: str,
    tree: Tree | None = None,
) -> frozenset[int]:
    """Return 1-indexed source lines that contain executable code."""
    source_lines = source.splitlines(keepends=True)
    text_lines = source.splitlines()
    lines: set[int] = set()
    for token in generate_tokens(iter(source_lines).__next__):
        if token.type not in IGNORED_SLOC_TOKEN_TYPES:
            lines.add(token.start[0])

    parsed_tree = tree if tree is not None else _parse_source_for_sloc(source)
    if parsed_tree is not None:
        for start, end in _string_ranges(parsed_tree.root_node, text_lines):
            for line_no in range(start, end + 1):
                lines.discard(line_no)

    return frozenset(lines)


def _parse_source_for_sloc(source: str) -> Tree | None:
    try:
        return parse_source(source)
    except ParseError:
        return None


def _string_ranges(root: Node, source_lines: list[str]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if (
            node.type == "expression_statement"
            and (literal := _string_literal(node)) is not None
            and _owns_line(literal, source_lines)
        ):
            ranges.append(
                (
                    literal.start_point[0] + 1,
                    literal.end_point[0] + 1,
                ),
            )

        stack.extend(reversed(node.named_children))

    return tuple(ranges)


def _string_literal(statement: Node) -> Node | None:
    if statement.type != "expression_statement":
        return None
    if len(statement.named_children) != 1:
        return None

    expression = statement.named_children[0]
    if expression.type == "string" and _is_plain_string_node(expression):
        return expression

    return None  # scbc ignore[redundant-return-none]


def _owns_line(
    literal: Node,
    source_lines: list[str],
) -> bool:
    start_row, start_col = literal.start_point
    end_row, end_col = literal.end_point
    start_line = (
        source_lines[start_row] if start_row < len(source_lines) else ""
    )
    end_line = source_lines[end_row] if end_row < len(source_lines) else ""

    return not start_line[:start_col].strip() and not end_line[end_col:].strip()


def _is_plain_string_node(node: Node) -> bool:
    text = node.text
    if text is None:
        return False

    prefix = _string_prefix(text.decode("utf-8"))
    return "b" not in prefix and "f" not in prefix


def _string_prefix(literal: str) -> str:
    prefix_chars: list[str] = []
    for character in literal:
        if character in {'"', "'"}:
            break
        prefix_chars.append(character.lower())
    return "".join(prefix_chars)

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.models import FunctionSymbol

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

COMPLEXITY_NODE_TYPES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "assert_statement",
        "list_comprehension",
        "set_comprehension",
        "dictionary_comprehension",
        "generator_expression",
        "boolean_operator",
        "conditional_expression",
        "if_clause",
    }
)


def extract_functions(
    file_path: Path,
    tree: Tree,
    sloc_lines: frozenset[int],
) -> tuple[FunctionSymbol, ...]:
    """Walk ``tree`` and emit a ``FunctionSymbol`` per function def.

    Cyclomatic complexity starts at 1 and increments for every node in
    ``COMPLEXITY_NODE_TYPES`` inside the function (including nested
    comprehensions, boolean operators, and conditional expressions).
    ``sloc`` counts the function's physical lines that are also present
    in ``sloc_lines``, so docstrings and blanks don't inflate it. Nested
    functions are emitted as siblings; methods are emitted flat with the
    class acting only as a traversal vehicle.
    """

    symbols: list[FunctionSymbol] = []
    _extract_functions_from_node(
        tree.root_node,
        file_path,
        sloc_lines,
        symbols,
        None,
    )
    return tuple(symbols)


def _extract_functions_from_node(
    node: Node,
    file_path: Path,
    sloc_lines: frozenset[int],
    symbols: list[FunctionSymbol],
    parent_class: str | None,
) -> None:
    for child in node.children:
        if child.type == "function_definition":
            _handle_function(
                child,
                file_path,
                sloc_lines,
                symbols,
            )
        elif child.type == "class_definition":
            _handle_class(child, file_path, sloc_lines, symbols)
        elif child.type == "decorated_definition" or child.type == "block":
            _extract_functions_from_node(
                child,
                file_path,
                sloc_lines,
                symbols,
                parent_class,
            )


def _handle_function(
    node: Node,
    file_path: Path,
    sloc_lines: frozenset[int],
    symbols: list[FunctionSymbol],
) -> None:
    name = _name_from_node(node)
    if name is None:
        return

    complexity = 1 + _count_complexity(node)
    sloc = _count_symbol_sloc(node, sloc_lines)
    symbols.append(
        FunctionSymbol(
            file=file_path,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            complexity=complexity,
            sloc=sloc,
        )
    )

    _extract_functions_from_node(node, file_path, sloc_lines, symbols, None)


def _handle_class(
    node: Node,
    file_path: Path,
    sloc_lines: frozenset[int],
    symbols: list[FunctionSymbol],
) -> None:
    class_name = _name_from_node(node)
    _extract_functions_from_node(
        node,
        file_path,
        sloc_lines,
        symbols,
        class_name,
    )


def _name_from_node(node: Node) -> str | None:
    name_node = next(
        (
            child
            for child in node.children
            if child.type in {"identifier", "name"}
        ),
        None,
    )
    text = name_node.text if name_node is not None else None
    return text.decode("utf-8") if text is not None else None


def _count_complexity(node: Node) -> int:
    complexity = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in COMPLEXITY_NODE_TYPES:
            complexity += 1
        stack.extend(current.children)
    return complexity


def _count_symbol_sloc(node: Node, sloc_lines: frozenset[int]) -> int:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return sum(1 for line_no in sloc_lines if start_line <= line_no <= end_line)

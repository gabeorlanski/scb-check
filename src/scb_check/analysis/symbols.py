"""Extract parsed symbols and complexity metrics from syntax trees."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.analysis.syntax import arguments_from_node
from scb_check.analysis.syntax import call_name
from scb_check.analysis.syntax import count_sloc_in_span
from scb_check.analysis.syntax import imports_from_node
from scb_check.analysis.syntax import iter_nodes
from scb_check.analysis.syntax import local_names
from scb_check.analysis.syntax import name_from_node
from scb_check.analysis.syntax import resolve_name
from scb_check.analysis.syntax import text
from scb_check.analysis.syntax import top_level_statements
from scb_check.models import ParsedSymbol
from scb_check.models import SymbolUsage

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree


CYC_COMPLEXITY_NODE_TYPES = frozenset(
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
    },
)

COG_FLOW_BREAK_TYPES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "else_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",
    },
)

COG_JUMP_TYPES = frozenset({"break_statement", "continue_statement"})


def extract_functions(
    file_path: Path,
    tree: Tree,
    sloc_lines: frozenset[int],
) -> tuple[ParsedSymbol, ...]:
    """Return parsed function symbols using a small tree-sitter visitor."""
    visitor = _SymbolVisitor(file_path, sloc_lines)
    return visitor.visit(tree.root_node)


class _SymbolVisitor:
    def __init__(self, file_path: Path, sloc_lines: frozenset[int]) -> None:
        self._file_path = file_path
        self._sloc_lines = sloc_lines
        self._imports: dict[str, str] = {}
        self._symbols: list[ParsedSymbol] = []

    def visit(self, root: Node) -> tuple[ParsedSymbol, ...]:
        self._visit_module_child(root)
        return tuple(self._symbols)

    def _visit_module_child(self, node: Node) -> None:
        for child in node.children:
            if child.type in {"import_statement", "import_from_statement"}:
                self._imports.update(imports_from_node(child))
            elif child.type == "function_definition":
                self._handle_symbol(child)
            elif child.type in {
                "class_definition",
                "decorated_definition",
                "block",
            }:
                self._visit_module_child(child)

    def _handle_symbol(self, node: Node) -> None:
        name = name_from_node(node)
        if name is None:
            return

        symbol = ParsedSymbol(
            name=name,
            file=self._file_path,
            start=(node.start_point.row + 1, node.start_point.column),
            end=(node.end_point.row + 1, node.end_point.column),
            node_type=node.type,
            statements=len(top_level_statements(node)),
            sloc=count_sloc_in_span(node, self._sloc_lines),
            cyc_complexity=1
            + sum(
                1
                for current in iter_nodes(node)
                if current.type in CYC_COMPLEXITY_NODE_TYPES
            ),
            cog_complexity=sum(
                _cognitive_for_node(child, nesting=0) for child in node.children
            ),
            agruments=arguments_from_node(node),
            returns=_return_annotation_from_node(node),
            usages=_symbol_usages(node, self._file_path, self._imports),
        )
        self._symbols.append(symbol)

        self._visit_module_child(node)



def _cognitive_for_node(node: Node, *, nesting: int) -> int:
    child_score = sum(
        _cognitive_for_node(child, nesting=nesting) for child in node.children
    )
    if node.type == "boolean_operator":
        return 1 + child_score
    if node.type in COG_JUMP_TYPES:
        return 1
    if node.type in COG_FLOW_BREAK_TYPES:
        nested_score = sum(
            _cognitive_for_node(child, nesting=nesting + 1)
            for child in node.children
        )
        return 1 + nesting + nested_score
    return child_score


def _return_annotation_from_node(node: Node) -> str | None:
    children = node.children
    return next(
        (
            text(children[index + 1])
            for index, child in enumerate(children[:-1])
            if child.type == "->"
        ),
        None,
    )


def _symbol_usages(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
) -> tuple[SymbolUsage, ...]:
    local = local_names(node)
    usages = tuple(
        _usage_from_call(call, file_path, imports)
        for call in iter_nodes(node)
        if call.type == "call"
    )
    return tuple(
        usage
        for usage in usages
        if usage is not None
        and usage.name.split(".", 1)[0] not in local
        and usage.name.split(".", 1)[0]
        not in {
            "bool",
            "dict",
            "float",
            "int",
            "len",
            "list",
            "print",
            "range",
            "set",
            "str",
            "super",
            "tuple",
        }
    )


def _usage_from_call(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
) -> SymbolUsage | None:
    name = call_name(node)
    usage = None
    if name is not None:
        usage = SymbolUsage(
            file=file_path,
            line=node.start_point[0] + 1,
            col=node.start_point[1],
            name=name,
            resolved_name=resolve_name(name, imports),
            kind="call",
        )
    return usage

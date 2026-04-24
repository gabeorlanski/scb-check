"""Extract parsed symbols and complexity metrics from syntax trees."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.models import ParsedSymbol

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Point
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

_SCOPE_NODE_TYPES = frozenset({"function_definition", "class_definition"})
_STATEMENT_SUFFIX = "_statement"
_MIN_ALIASED_IMPORT_PARTS = 2

_BUILTIN_CALLS = frozenset(
    {
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
    },
)


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
                self._imports.update(_imports_from_node(child))
            elif child.type == "function_definition":
                self._handle_symbol(child)
            elif child.type in {
                "class_definition",
                "decorated_definition",
                "block",
            }:
                self._visit_module_child(child)

    def _handle_symbol(self, node: Node) -> None:
        name = _name_from_node(node)
        if name is None:
            return

        local_names = _local_names(node)
        calls = Counter(
            _resolve_call_name(call_name, self._imports)
            for call in _iter_nodes(node)
            if call.type == "call"
            for call_name in [_call_name(call)]
            if call_name is not None
            and _root_name(call_name) not in local_names
            and _root_name(call_name) not in _BUILTIN_CALLS
        )

        symbol = ParsedSymbol(
            name=name,
            file=self._file_path,
            start=_point(node.start_point),
            end=_point(node.end_point),
            node_type=node.type,
            statements=_top_level_statement_count(node),
            sloc=_count_symbol_sloc(node, self._sloc_lines),
            cyc_complexity=1 + _count_cyclomatic_complexity(node),
            cog_complexity=_cognitive_complexity(node),
            agruments=_arguments_from_node(node),
            returns=_return_annotation_from_node(node),
            calls=calls,
        )
        self._symbols.append(symbol)

        self._visit_module_child(node)


def _iter_nodes(node: Node) -> tuple[Node, ...]:
    nodes: list[Node] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(current.children))
    return tuple(nodes)


def _name_from_node(node: Node) -> str | None:
    name_node = next(
        (
            child
            for child in node.children
            if child.type in {"identifier", "name"}
        ),
        None,
    )
    return _text(name_node) if name_node is not None else None


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8")


def _point(point: Point) -> tuple[int, int]:
    return (point.row + 1, point.column)


def _count_cyclomatic_complexity(node: Node) -> int:
    return sum(
        1
        for current in _iter_nodes(node)
        if current.type in CYC_COMPLEXITY_NODE_TYPES
    )


def _cognitive_complexity(node: Node) -> int:
    return _cognitive_for_children(node, nesting=0)


def _cognitive_for_children(node: Node, *, nesting: int) -> int:
    return sum(
        _cognitive_for_node(child, nesting=nesting) for child in node.children
    )


def _cognitive_for_node(node: Node, *, nesting: int) -> int:
    if node.type == "boolean_operator":
        return 1 + _cognitive_for_children(node, nesting=nesting)
    if node.type in COG_JUMP_TYPES:
        return 1
    if node.type in COG_FLOW_BREAK_TYPES:
        return 1 + nesting + _cognitive_for_children(node, nesting=nesting + 1)
    return _cognitive_for_children(node, nesting=nesting)


def _count_symbol_sloc(node: Node, sloc_lines: frozenset[int]) -> int:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return sum(1 for line_no in sloc_lines if start_line <= line_no <= end_line)


def _top_level_statement_count(node: Node) -> int:
    block = _body_block(node)
    if block is None:
        return 0
    return sum(1 for child in block.children if _is_statement(child))


def _body_block(node: Node) -> Node | None:
    return next(
        (child for child in node.children if child.type == "block"), None,
    )


def _is_statement(node: Node) -> bool:
    return node.type.endswith(_STATEMENT_SUFFIX) or node.type in {
        "function_definition",
        "class_definition",
        "decorated_definition",
    }


def _arguments_from_node(node: Node) -> dict[str, str | None]:
    params = next(
        (child for child in node.children if child.type == "parameters"), None,
    )
    if params is None:
        return {}
    return {
        name: annotation
        for child in params.children
        for parsed in [_parse_parameter(child)]
        if parsed is not None
        for name, annotation in [parsed]
    }


def _parse_parameter(node: Node) -> tuple[str, str | None] | None:
    if node.type == "identifier":
        return (_text(node), None)
    if node.type not in {
        "typed_parameter",
        "default_parameter",
        "typed_default_parameter",
        "list_splat_pattern",
        "dictionary_splat_pattern",
    }:
        return None
    name_node = next(
        (child for child in node.children if child.type == "identifier"),
        None,
    )
    if name_node is None:
        return None
    type_node = next(
        (child for child in node.children if child.type == "type"), None,
    )
    return (
        _text(name_node),
        _text(type_node) if type_node is not None else None,
    )

def _return_annotation_from_node(node: Node) -> str | None:
    children = node.children
    return next(
        (
            _text(children[index + 1])
            for index, child in enumerate(children[:-1])
            if child.type == "->"
        ),
        None,
    )


def _local_names(node: Node) -> set[str]:
    names = {_name_from_node(node) or ""}
    names.update(_arguments_from_node(node))
    for current in _iter_nodes(node):
        if current is node:
            continue
        if current.type in _SCOPE_NODE_TYPES:
            name = _name_from_node(current)
            if name is not None:
                names.add(name)
    names.discard("")
    return names


def _call_name(node: Node) -> str | None:
    target = next(
        (
            child
            for child in node.children
            if child.type not in {"argument_list", "(", ")", ","}
        ),
        None,
    )
    if target is None:
        return None
    if target.type in {"identifier", "attribute"}:
        return _text(target)
    return None


def _root_name(name: str) -> str:
    return name.split(".", 1)[0]


def _resolve_call_name(name: str, imports: dict[str, str]) -> str:
    root = _root_name(name)
    if root not in imports:
        return name
    if root == name:
        return imports[root]
    return imports[root] + name[len(root) :]


def _imports_from_node(node: Node) -> dict[str, str]:
    if node.type == "import_statement":
        return _import_statement_names(node)
    if node.type == "import_from_statement":
        return _import_from_statement_names(node)
    return {}


def _import_statement_names(node: Node) -> dict[str, str]:
    imports: dict[str, str] = {}
    for child in node.children:
        match child.type:
            case "dotted_name":
                full_name = _text(child)
                imports[full_name.split(".", 1)[0]] = full_name
            case "aliased_import":
                if parts := _aliased_import_parts(child):
                    imported, alias = parts
                    imports[alias] = imported
    return imports


def _import_from_statement_names(node: Node) -> dict[str, str]:
    module = next(
        (child for child in node.children if child.type == "dotted_name"), None,
    )
    module_name = _text(module) if module is not None else ""
    imports: dict[str, str] = {}
    for child in node.children:
        if child is module:
            continue
        match child.type:
            case "dotted_name":
                imported = _text(child)
                imports[imported] = _qualified_import(module_name, imported)
            case "aliased_import":
                if parts := _aliased_import_parts(child):
                    imported, alias = parts
                    imports[alias] = _qualified_import(module_name, imported)
    return imports


def _aliased_import_parts(node: Node) -> tuple[str, str] | None:
    names = [
        child
        for child in node.children
        if child.type in {"dotted_name", "identifier"}
    ]
    if len(names) >= _MIN_ALIASED_IMPORT_PARTS:
        return (_text(names[0]), _text(names[-1]))
    return None


def _qualified_import(module_name: str, imported: str) -> str:
    return f"{module_name}.{imported}" if module_name else imported

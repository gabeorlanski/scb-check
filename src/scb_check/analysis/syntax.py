"""Shared tree-sitter helpers for Python analysis."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.analysis.strings import string_prefix

if TYPE_CHECKING:
    from tree_sitter import Node

_SCOPE_NODE_TYPES = frozenset({"function_definition", "class_definition"})
_STATEMENT_SUFFIX = "_statement"
_MIN_ALIASED_IMPORT_PARTS = 2



def iter_nodes(node: Node) -> tuple[Node, ...]:
    """Return `node` and descendants in source order."""
    nodes: list[Node] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(current.children))
    return tuple(nodes)


def text(node: Node) -> str:
    """Return UTF-8 source text for `node`."""
    source = node.text or b""
    return source.decode("utf-8")


def name_from_node(node: Node) -> str | None:
    """Return the first identifier-like child name for a definition node."""
    name_node = next(
        (
            child
            for child in node.children
            if child.type in {"identifier", "name"}
        ),
        None,
    )
    return text(name_node) if name_node is not None else None


def top_level_statements(node: Node) -> tuple[Node, ...]:
    """Return statement children directly inside a function/class body."""
    block = next(
        (child for child in node.children if child.type == "block"), None,
    )
    if block is None:
        return ()
    return tuple(
        child
        for child in block.children
        if child.type.endswith(_STATEMENT_SUFFIX)
        or child.type
        in {
            "function_definition",
            "class_definition",
            "decorated_definition",
        }
    )


# scbc ignore[trivial-wrapper] Shared syntax helper used by wrapper detection.
def executable_body_statements(node: Node) -> tuple[Node, ...]:
    """Return body statements excluding plain string docstring statements."""
    return tuple(
        statement
        for statement in top_level_statements(node)
        if not is_plain_string_expression_statement(statement)
    )


def is_plain_string_expression_statement(statement: Node) -> bool:
    """Return True for standalone non-f-string/non-bytes string statements."""
    if statement.type != "expression_statement":
        return False
    if len(statement.named_children) != 1:
        return False

    expression = statement.named_children[0]
    if expression.type != "string":
        return False

    node_text = expression.text
    if node_text is None:
        return False

    prefix = string_prefix(node_text.decode("utf-8"))
    return "b" not in prefix and "f" not in prefix


def count_sloc_in_span(node: Node, sloc_lines: frozenset[int]) -> int:
    """Count supplied SLOC lines inside `node`'s line span."""
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return sum(1 for line_no in sloc_lines if start_line <= line_no <= end_line)


def arguments_from_node(node: Node) -> dict[str, str | None]:
    """Return parameter names and annotations for a function node."""
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


def local_names(node: Node) -> set[str]:
    """Return names local to a function for call/reference filtering."""
    names = {name_from_node(node) or ""}
    names.update(arguments_from_node(node))
    for current in iter_nodes(node):
        if current is node:
            continue
        if current.type in _SCOPE_NODE_TYPES:
            name = name_from_node(current)
            if name is not None:
                names.add(name)
    names.discard("")
    return names


def call_name(node: Node) -> str | None:
    """Return the textual callee name for a call node."""
    target = call_target(node)
    name = None
    if target is not None and target.type in {"identifier", "attribute"}:
        name = text(target)
    return name


# scbc ignore[trivial-wrapper] Names the callee-node lookup.
def call_target(node: Node) -> Node | None:
    """Return the callee node for a call node."""
    return next(
        (
            child
            for child in node.children
            if child.type not in {"argument_list", "(", ")", ","}
        ),
        None,
    )


def resolve_name(name: str, imports: dict[str, str]) -> str:
    """Resolve an imported dotted name through `imports`."""
    root = name.split(".", 1)[0]
    if root not in imports:
        return name
    return imports[root] if root == name else f"{imports[root]}{name[len(root) :]}"


def imports_from_node(node: Node) -> dict[str, str]:
    """Return imported local-name to qualified-name mappings."""
    if node.type == "import_statement":
        return _import_statement_names(node)
    if node.type == "import_from_statement":
        return _import_from_statement_names(node)
    return {}


def module_name_for_path(path: Path) -> str:
    """Return a best-effort import module name for `path`."""
    package_parts = _package_parts(path.parent)
    if path.name == "__init__.py":
        return ".".join(package_parts) if package_parts else path.parent.name
    return ".".join((*package_parts, path.stem)) if package_parts else path.stem


def _parse_parameter(node: Node) -> tuple[str, str | None] | None:
    if node.type == "identifier":
        return (text(node), None)
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
        text(name_node),
        text(type_node) if type_node is not None else None,
    )


def _package_parts(directory: Path) -> tuple[str, ...]:
    parts: list[str] = []
    current = directory
    while (current / "__init__.py").exists():
        parts.append(current.name)
        current = current.parent
    return tuple(reversed(parts))


def _import_statement_names(node: Node) -> dict[str, str]:
    imports: dict[str, str] = {}
    for child in node.children:
        match child.type:
            case "dotted_name":
                full_name = text(child)
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
    module_name = text(module) if module is not None else ""
    imports: dict[str, str] = {}
    for child in node.children:
        if child is not module:
            _add_import_from_child(imports, child, module_name)
    return imports


def _add_import_from_child(
    imports: dict[str, str],
    child: Node,
    module_name: str,
) -> None:
    match child.type:
        case "dotted_name":
            imported = text(child)
            imports[imported] = (
                f"{module_name}.{imported}" if module_name else imported
            )
        case "aliased_import":
            if parts := _aliased_import_parts(child):
                imported, alias = parts
                imports[alias] = (
                    f"{module_name}.{imported}" if module_name else imported
                )


def _aliased_import_parts(node: Node) -> tuple[str, str] | None:
    names = [
        child
        for child in node.children
        if child.type in {"dotted_name", "identifier"}
    ]
    if len(names) >= _MIN_ALIASED_IMPORT_PARTS:
        return (text(names[0]), text(names[-1]))
    return None  # scbc ignore[redundant-return-none]

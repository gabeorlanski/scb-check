"""Detect trivial wrapper functions and function aliases."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.analysis.syntax import arguments_from_node
from scb_check.analysis.syntax import call_name
from scb_check.analysis.syntax import call_target
from scb_check.analysis.syntax import executable_body_statements
from scb_check.analysis.syntax import imports_from_node
from scb_check.analysis.syntax import iter_nodes
from scb_check.analysis.syntax import module_name_for_path
from scb_check.analysis.syntax import name_from_node
from scb_check.analysis.syntax import resolve_name
from scb_check.analysis.syntax import text
from scb_check.models import ParsedSymbol
from scb_check.models import SymbolUsage
from scb_check.models import TrivialWrapper

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

TRIVIAL_WRAPPER_RULE_ID = "trivial-wrapper"
_FUNCTION_ALIAS_KIND = "function_alias"
_SINGLE_RETURN_KIND = "single_return_function"
_ALIAS_ASSIGNMENT_PARTS = 2
_RECEIVER_PARAMETER_NAMES = frozenset({"self", "cls"})
_SKIP_USAGE_ANCESTOR_TYPES = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "parameters",
    },
)


@dataclass(frozen=True, slots=True)
class _FileContext:
    module: str
    file_path: Path
    imports: dict[str, str]
    definitions: dict[str, str]
    function_qnames: frozenset[str]


def detect_trivial_wrappers(
    parsed_files: tuple[tuple[Path, str, Tree], ...],
    functions: tuple[ParsedSymbol, ...],
) -> tuple[TrivialWrapper, ...]:
    """Return trivial wrapper findings with usages resolved within scanned files."""
    module_by_file = {
        file_path: module_name_for_path(file_path)
        for file_path, _, _ in parsed_files
    }
    imports_by_file = _imports_by_file(parsed_files)
    function_names_by_file = _function_names_by_file(functions, module_by_file)
    function_qnames = frozenset(
        qualified
        for definitions in function_names_by_file.values()
        for qualified in definitions.values()
    )

    function_wrappers = _single_return_function_wrappers(
        parsed_files,
        module_by_file,
        imports_by_file,
        function_names_by_file,
        function_qnames,
    )
    aliases = _function_aliases(
        parsed_files,
        module_by_file,
        imports_by_file,
        function_names_by_file,
        function_qnames,
    )
    wrappers = tuple(
        sorted(
            (*function_wrappers, *aliases),
            key=lambda wrapper: (
                wrapper.file.as_posix(),
                wrapper.start_line,
                wrapper.col,
                wrapper.name,
            ),
        ),
    )
    tracked_names = frozenset(wrapper.qualified_name for wrapper in wrappers)
    local_defs_by_file = _local_defs_by_file(
        function_names_by_file,
        aliases,
    )
    usages_by_name = _usages_by_name(
        parsed_files,
        imports_by_file,
        local_defs_by_file,
        tracked_names,
    )
    return tuple(
        replace(wrapper, usages=usages_by_name.get(wrapper.qualified_name, ()))
        for wrapper in wrappers
    )


def _imports_by_file(
    parsed_files: tuple[tuple[Path, str, Tree], ...],
) -> dict[Path, dict[str, str]]:
    imports: dict[Path, dict[str, str]] = {}
    for file_path, _, tree in parsed_files:
        file_imports: dict[str, str] = {}
        for child in tree.root_node.children:
            if child.type in {"import_statement", "import_from_statement"}:
                file_imports.update(imports_from_node(child))
        imports[file_path] = file_imports
    return imports


def _function_names_by_file(
    functions: tuple[ParsedSymbol, ...],
    module_by_file: dict[Path, str],
) -> dict[Path, dict[str, str]]:
    names_by_file: dict[Path, dict[str, str]] = {}
    for symbol in functions:
        module = module_by_file[symbol.file]
        names_by_file.setdefault(symbol.file, {})[symbol.name] = (
            f"{module}.{symbol.name}"
        )
    return names_by_file


def _file_context(
    file_path: Path,
    module_by_file: dict[Path, str],
    imports_by_file: dict[Path, dict[str, str]],
    function_names_by_file: dict[Path, dict[str, str]],
    function_qnames: frozenset[str],
) -> _FileContext:
    return _FileContext(
        module=module_by_file[file_path],
        file_path=file_path,
        imports=imports_by_file[file_path],
        definitions=function_names_by_file.get(  # scbc ignore[dict-get-empty-dict-default]
            file_path,
            {},
        ),
        function_qnames=function_qnames,
    )


def _single_return_function_wrappers(
    parsed_files: tuple[tuple[Path, str, Tree], ...],
    module_by_file: dict[Path, str],
    imports_by_file: dict[Path, dict[str, str]],
    function_names_by_file: dict[Path, dict[str, str]],
    function_qnames: frozenset[str],
) -> tuple[TrivialWrapper, ...]:
    wrappers: list[TrivialWrapper] = []
    for file_path, _, tree in parsed_files:
        context = _file_context(
            file_path,
            module_by_file,
            imports_by_file,
            function_names_by_file,
            function_qnames,
        )
        wrappers.extend(
            wrapper
            for node in iter_nodes(tree.root_node)
            if (wrapper := _single_return_wrapper(node, context)) is not None
        )
    return tuple(wrappers)


def _single_return_wrapper(
    node: Node,
    context: _FileContext,
) -> TrivialWrapper | None:
    if node.type != "function_definition":
        return None

    name = name_from_node(node)
    if name is None:
        return None

    expression = _single_return_expression(node)
    if expression is None:
        return None

    if not _is_removable_single_return(node, name, expression, context):
        return None

    return TrivialWrapper(
        file=context.file_path,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        col=node.start_point[1],
        end_col=node.end_point[1],
        name=name,
        qualified_name=f"{context.module}.{name}",
        kind=_SINGLE_RETURN_KIND,
    )


def _single_return_expression(node: Node) -> Node | None:
    executable_statements = executable_body_statements(node)
    if len(executable_statements) != 1:
        return None

    statement = executable_statements[0]
    if statement.type != "return_statement" or len(statement.named_children) != 1:
        return None
    return statement.named_children[0]


def _is_removable_single_return(
    node: Node,
    name: str,
    expression: Node,
    context: _FileContext,
) -> bool:
    method_class = _method_class(node)
    if _is_required_api_function(node, name, method_class):
        return False

    parameter_names = _forwardable_parameter_names(node, method_class)
    return _returns_forwarded_parameter(
        expression,
        parameter_names,
    ) or _returns_passthrough_project_call(
        expression,
        parameter_names,
        name,
        context,
    )


def _is_required_api_function(
    node: Node,
    name: str,
    method_class: Node | None,
) -> bool:
    # Decorators and inherited methods are often framework or parent-class API
    # surfaces; a pass-through body does not mean the function can be removed.
    return (
        (node.parent is not None and node.parent.type == "decorated_definition")
        or _is_dunder_name(name)
        or (method_class is not None and _class_has_explicit_base(method_class))
    )


def _is_dunder_name(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _forwardable_parameter_names(
    node: Node,
    method_class: Node | None,
) -> frozenset[str]:
    parameter_names = frozenset(arguments_from_node(node))
    if method_class is None:
        return parameter_names
    return parameter_names - _RECEIVER_PARAMETER_NAMES


def _returns_forwarded_parameter(
    expression: Node,
    parameter_names: frozenset[str],
) -> bool:
    return expression.type == "identifier" and text(expression) in parameter_names


def _returns_passthrough_project_call(
    expression: Node,
    parameter_names: frozenset[str],
    name: str,
    context: _FileContext,
) -> bool:
    if expression.type != "call" or not parameter_names:
        return False

    raw_callee = call_name(expression)
    if raw_callee is None:
        return False

    resolved_callee = _resolve_reference(
        raw_callee,
        context.imports,
        context.definitions,
    )
    if (
        resolved_callee not in context.function_qnames
        or resolved_callee == f"{context.module}.{name}"
    ):
        return False

    argument_names = _passthrough_argument_names(expression)
    return (
        argument_names is not None
        and len(argument_names) == len(parameter_names)
        and frozenset(argument_names) == parameter_names
    )


def _passthrough_argument_names(call: Node) -> tuple[str, ...] | None:
    argument_list = next(
        (child for child in call.children if child.type == "argument_list"),
        None,
    )
    if argument_list is None:
        return ()

    names: list[str] = []
    for child in argument_list.named_children:
        name = _passthrough_argument_name(child)
        if name is None:
            return None
        names.append(name)
    return tuple(names)


def _passthrough_argument_name(node: Node) -> str | None:
    name = None
    if node.type == "identifier":
        name = text(node)
    elif node.type in {"list_splat", "dictionary_splat"}:
        name = _single_identifier_child_text(node)
    elif node.type == "keyword_argument" and node.named_children:
        value = node.named_children[-1]
        if value.type == "identifier":
            name = text(value)
    return name


def _single_identifier_child_text(node: Node) -> str | None:
    child = next(
        (child for child in node.named_children if child.type == "identifier"),
        None,
    )
    return text(child) if child is not None else None


def _method_class(node: Node) -> Node | None:
    current = node.parent
    method_class = None
    while current is not None and method_class is None:
        if current.type == "function_definition":
            break
        if current.type == "class_definition":
            method_class = current
        current = current.parent
    return method_class


def _class_has_explicit_base(node: Node) -> bool:
    argument_list = next(
        (child for child in node.children if child.type == "argument_list"),
        None,
    )
    return argument_list is not None and bool(argument_list.named_children)


def _function_aliases(
    parsed_files: tuple[tuple[Path, str, Tree], ...],
    module_by_file: dict[Path, str],
    imports_by_file: dict[Path, dict[str, str]],
    function_names_by_file: dict[Path, dict[str, str]],
    function_qnames: frozenset[str],
) -> tuple[TrivialWrapper, ...]:
    aliases: list[TrivialWrapper] = []
    for file_path, _, tree in parsed_files:
        context = _file_context(
            file_path,
            module_by_file,
            imports_by_file,
            function_names_by_file,
            function_qnames,
        )
        for statement in tree.root_node.children:
            alias = _alias_from_statement(statement, context)
            if alias is not None:
                aliases.append(alias)
    return tuple(aliases)


def _alias_from_statement(
    statement: Node,
    context: _FileContext,
) -> TrivialWrapper | None:
    alias = None
    assignment = _assignment_from_statement(statement)
    has_alias_parts = (
        assignment is not None
        and len(assignment.named_children) == _ALIAS_ASSIGNMENT_PARTS
    )
    if has_alias_parts and assignment is not None:
        target, value = assignment.named_children
        if target.type == "identifier" and value.type in {"identifier", "attribute"}:
            resolved_value = _resolve_reference(
                text(value),
                context.imports,
                context.definitions,
            )
            if resolved_value in context.function_qnames:
                name = text(target)
                alias = TrivialWrapper(
                    file=context.file_path,
                    start_line=statement.start_point[0] + 1,
                    end_line=statement.end_point[0] + 1,
                    col=statement.start_point[1],
                    end_col=statement.end_point[1],
                    name=name,
                    qualified_name=f"{context.module}.{name}",
                    kind=_FUNCTION_ALIAS_KIND,
                )
    return alias


def _assignment_from_statement(statement: Node) -> Node | None:
    assignment = None
    if statement.type == "expression_statement" and len(statement.named_children) == 1:
        child = statement.named_children[0]
        if child.type == "assignment":
            assignment = child
    return assignment


def _local_defs_by_file(
    function_names_by_file: dict[Path, dict[str, str]],
    aliases: tuple[TrivialWrapper, ...],
) -> dict[Path, dict[str, str]]:
    definitions = {
        file_path: dict(file_definitions)
        for file_path, file_definitions in function_names_by_file.items()
    }
    for alias in aliases:
        file_definitions = definitions.setdefault(alias.file, {})
        file_definitions[alias.name] = alias.qualified_name
    return definitions


def _usages_by_name(
    parsed_files: tuple[tuple[Path, str, Tree], ...],
    imports_by_file: dict[Path, dict[str, str]],
    local_defs_by_file: dict[Path, dict[str, str]],
    tracked_names: frozenset[str],
) -> dict[str, tuple[SymbolUsage, ...]]:
    usages: dict[str, list[SymbolUsage]] = {name: [] for name in tracked_names}
    for file_path, _, tree in parsed_files:
        imports = imports_by_file[file_path]
        definitions = local_defs_by_file.get(  # scbc ignore[dict-get-empty-dict-default]
            file_path,
            {},
        )
        call_target_spans = _call_target_spans(tree.root_node)
        for node in iter_nodes(tree.root_node):
            usage = _usage_from_node(
                node,
                file_path,
                imports,
                definitions,
                call_target_spans,
            )
            if usage is None or usage.resolved_name not in tracked_names:
                continue
            usages[usage.resolved_name].append(usage)
    return {
        name: tuple(
            sorted(
                name_usages,
                key=lambda usage: (
                    usage.file.as_posix(),
                    usage.line,
                    usage.col,
                    usage.kind,
                    usage.name,
                ),
            ),
        )
        for name, name_usages in usages.items()
    }


# scbc ignore[trivial-wrapper] Names the call-target span projection for usage filtering.
def _call_target_spans(root: Node) -> frozenset[tuple[int, int]]:
    return frozenset(
        (target.start_byte, target.end_byte)
        for node in iter_nodes(root)
        if node.type == "call"
        for target in [call_target(node)]
        if target is not None
    )


def _usage_from_node(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
    definitions: dict[str, str],
    call_target_spans: frozenset[tuple[int, int]],
) -> SymbolUsage | None:
    usage = None
    if node.type == "call":
        usage = _usage_from_call(node, file_path, imports, definitions)
    elif (
        node.type in {"identifier", "attribute"}
        and (node.start_byte, node.end_byte) not in call_target_spans
        and not _is_reference_excluded(node)
    ):
        raw_name = text(node)
        usage = SymbolUsage(
            file=file_path,
            line=node.start_point[0] + 1,
            col=node.start_point[1],
            name=raw_name,
            resolved_name=_resolve_reference(raw_name, imports, definitions),
            kind="reference",
        )
    return usage


def _usage_from_call(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
    definitions: dict[str, str],
) -> SymbolUsage | None:
    usage = None
    raw_name = call_name(node)
    if raw_name is not None:
        target = call_target(node) or node
        usage = SymbolUsage(
            file=file_path,
            line=target.start_point[0] + 1,
            col=target.start_point[1],
            name=raw_name,
            resolved_name=_resolve_reference(raw_name, imports, definitions),
            kind="call",
        )
    return usage


def _resolve_reference(
    raw_name: str,
    imports: dict[str, str],
    definitions: dict[str, str],
) -> str:
    root = raw_name.split(".", 1)[0]
    if root in definitions:
        return (
            definitions[root]
            if root == raw_name
            else f"{definitions[root]}{raw_name[len(root) :]}"
        )
    return resolve_name(raw_name, imports)


# scbc ignore[trivial-wrapper] Names the reference exclusion predicate.
def _is_reference_excluded(node: Node) -> bool:
    return (
        _has_ancestor_type(node, _SKIP_USAGE_ANCESTOR_TYPES)
        or (node.parent is not None and node.parent.type == "attribute")
        or _is_assignment_target(node)
        or _is_function_definition_name(node)
    )


def _has_ancestor_type(node: Node, excluded_types: frozenset[str]) -> bool:
    current = node.parent
    found = False
    while current is not None and not found:
        found = current.type in excluded_types
        current = current.parent
    return found


def _is_assignment_target(node: Node) -> bool:
    parent = node.parent
    is_target = False
    if parent is not None and parent.type == "assignment":
        is_target = bool(parent.named_children and parent.named_children[0] == node)
    return is_target


def _is_function_definition_name(node: Node) -> bool:
    parent = node.parent
    is_name = False
    if parent is not None and parent.type == "function_definition":
        is_name = name_from_node(parent) == text(node)
    return is_name

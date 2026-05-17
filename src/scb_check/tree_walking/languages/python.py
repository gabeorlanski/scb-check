"""Python tree-sitter parser that emits language-agnostic IR."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from token import COMMENT
from token import DEDENT
from token import ENDMARKER
from token import INDENT
from token import NEWLINE
from token import NL
from tokenize import generate_tokens
from typing import TYPE_CHECKING

import tree_sitter_python
from tree_sitter import Language as TreeSitterLanguage
from tree_sitter import Parser

from scb_check.tree_walking.artifacts import LanguageParseError
from scb_check.tree_walking.artifacts import ParsedFile
from scb_check.tree_walking.languages._node_helpers import (
    count_sloc_in_span as _count_sloc_in_span,
)
from scb_check.tree_walking.languages._node_helpers import (
    iter_nodes as _iter_nodes,
)
from scb_check.tree_walking.languages._node_helpers import (
    module_span as _module_span,
)
from scb_check.tree_walking.languages._node_helpers import (
    node_span as _node_span,
)
from scb_check.tree_walking.languages._node_helpers import (
    qualified_name as _qualified_name,
)
from scb_check.tree_walking.languages._node_helpers import text as _text
from scb_check.tree_walking.models import ImportIR
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import ModuleIR
from scb_check.tree_walking.models import OperationIR
from scb_check.tree_walking.models import OperationKind
from scb_check.tree_walking.models import ReferenceIR
from scb_check.tree_walking.models import SignatureIR
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.models import SymbolRole
from scb_check.tree_walking.models import ValueIR
from scb_check.tree_walking.models import ValueKind

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

_CYC_COMPLEXITY_NODE_TYPES = frozenset(
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
_COG_FLOW_BREAK_TYPES = frozenset(
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
_COG_JUMP_TYPES = frozenset({"break_statement", "continue_statement"})
_SCOPE_NODE_TYPES = frozenset({"function_definition", "class_definition"})
_STATEMENT_SUFFIX = "_statement"
_LITERAL_TYPES = frozenset(
    {
        "string",
        "integer",
        "float",
        "imaginary",
        "true",
        "false",
        "none",
    },
)
_COLLECTION_TYPES = frozenset(
    {
        "list",
        "tuple",
        "dictionary",
        "set",
        "list_comprehension",
        "set_comprehension",
        "dictionary_comprehension",
        "generator_expression",
    },
)
_OPERATOR_TYPES = frozenset(
    {
        "binary_operator",
        "boolean_operator",
        "comparison_operator",
        "not_operator",
        "unary_operator",
        "conditional_expression",
    },
)
_STATEMENT_OPERATION_KINDS = {
    "return_statement": OperationKind.RETURN,
    "if_statement": OperationKind.BRANCH,
    "match_statement": OperationKind.BRANCH,
    "try_statement": OperationKind.BRANCH,
    "for_statement": OperationKind.LOOP,
    "while_statement": OperationKind.LOOP,
    "raise_statement": OperationKind.RAISE,
}
_EXPRESSION_OPERATION_KINDS = {
    "assignment": OperationKind.ASSIGN,
    "call": OperationKind.CALL,
}
_BUILTIN_CALL_ROOTS = frozenset(
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
_IGNORED_SLOC_TOKEN_TYPES = {
    COMMENT,
    DEDENT,
    ENDMARKER,
    INDENT,
    NEWLINE,
    NL,
}
_MIN_ALIASED_IMPORT_PARTS = 2
_RECEIVER_PARAMETER_NAMES = frozenset({"self", "cls"})

_PARSER: Parser | None = None


@dataclass(frozen=True, slots=True)
class ClassContext:
    """Enclosing class facts used while walking Python symbols."""

    qualified_name: str
    base_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VisitContext:
    """Current ownership and decorator context during tree walking."""

    owner_qualified_name: str | None = None
    class_context: ClassContext | None = None
    decorators: tuple[str, ...] = ()


class PythonParser:
    """Parse Python source into `ModuleIR`."""

    language = Language.PYTHON

    def parse(self, file_path: Path, source: str) -> ParsedFile:
        """Parse already-read Python `source`."""
        tree = _parse_tree(source)
        sloc_lines = _sloc_line_numbers(source, tree)
        walker = PythonWalker(file_path, source, tree, sloc_lines)
        return ParsedFile(
            file=file_path,
            source=source,
            module=walker.module(),
            native_tree=tree,
        )


class PythonWalker:
    """Walk a Python tree-sitter tree into generic module IR."""

    def __init__(
        self,
        file_path: Path,
        source: str,
        tree: Tree,
        sloc_lines: frozenset[int],
    ) -> None:
        """Initialize the walker with source and precomputed SLOC lines."""
        self._file_path = file_path
        self._source = source
        self._source_lines = source.splitlines()
        self._tree = tree
        self._sloc_lines = sloc_lines
        self._module_name = _module_name_for_path(file_path)
        self._imports = _imports_from_root(file_path, tree.root_node)
        self._imports_by_name = {
            import_.local_name: import_.qualified_name for import_ in self._imports
        }
        self._symbols: list[SymbolIR] = []

    def module(self) -> ModuleIR:
        """Return the parsed module IR."""
        self._visit_children(self._tree.root_node, VisitContext())
        return ModuleIR(
            language=Language.PYTHON,
            file=self._file_path,
            module_name=self._module_name,
            span=_module_span(self._file_path, self._source_lines),
            imports=self._imports,
            symbols=tuple(self._symbols),
            references=tuple(
                reference
                for symbol in self._symbols
                for reference in symbol.references
            ),
            sloc_lines=self._sloc_lines,
        )

    def _visit_children(self, node: Node, context: VisitContext) -> None:
        for child in node.children:
            self._visit_child(child, context)

    def _visit_child(self, child: Node, context: VisitContext) -> None:
        match child.type:
            case "import_statement" | "import_from_statement":
                return
            case "decorated_definition":
                self._visit_decorated_definition(child, context)
            case "class_definition":
                self._handle_class(child, context)
            case "function_definition":
                self._handle_function(child, context)
            case "block":
                self._visit_children(child, context)

    def _visit_decorated_definition(
        self,
        node: Node,
        context: VisitContext,
    ) -> None:
        decorators = tuple(
            _decorator_name(child) for child in node.children if child.type == "decorator"
        )
        definition = next(
            (
                child
                for child in node.children
                if child.type in {"function_definition", "class_definition"}
            ),
            None,
        )
        if definition is None:
            return
        decorated_context = VisitContext(
            owner_qualified_name=context.owner_qualified_name,
            class_context=context.class_context,
            decorators=decorators,
        )
        if definition.type == "class_definition":
            self._handle_class(definition, decorated_context)
            return
        self._handle_function(definition, decorated_context)

    def _handle_class(self, node: Node, context: VisitContext) -> None:
        name = _name_from_node(node)
        if name is None:
            return
        qualified_name = _qualified_name(
            self._module_name,
            context.owner_qualified_name,
            name,
        )
        base_names = _class_base_names(node)
        class_symbol = SymbolIR(
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.CLASS,
            span=_node_span(self._file_path, node),
            language=Language.PYTHON,
            roles=frozenset(),
            owner_qualified_name=context.owner_qualified_name,
            base_names=base_names,
            sloc=_count_sloc_in_span(node, self._sloc_lines),
        )
        self._symbols.append(class_symbol)
        class_context = ClassContext(
            qualified_name=qualified_name,
            base_names=base_names,
        )
        self._visit_children(
            node,
            VisitContext(
                owner_qualified_name=qualified_name,
                class_context=class_context,
            ),
        )

    def _handle_function(self, node: Node, context: VisitContext) -> None:
        name = _name_from_node(node)
        if name is None:
            return
        qualified_name = _qualified_name(
            self._module_name,
            context.owner_qualified_name,
            name,
        )
        signature = _signature_from_node(node)
        symbol = SymbolIR(
            name=name,
            qualified_name=qualified_name,
            kind=(
                SymbolKind.METHOD
                if context.class_context is not None
                else SymbolKind.FUNCTION
            ),
            span=_node_span(self._file_path, node),
            language=Language.PYTHON,
            roles=_function_roles(name, context),
            signature=signature,
            body=_body_operations(self._file_path, node, self._imports_by_name),
            references=_symbol_references(
                node,
                self._file_path,
                self._imports_by_name,
            ),
            owner_qualified_name=context.owner_qualified_name,
            base_names=(
                context.class_context.base_names
                if context.class_context is not None
                else ()
            ),
            sloc=_count_sloc_in_span(node, self._sloc_lines),
            cyc_complexity=1
            + sum(
                1
                for current in _iter_nodes(node)
                if current.type in _CYC_COMPLEXITY_NODE_TYPES
            ),
            cog_complexity=sum(
                _cognitive_for_node(child, nesting=0) for child in node.children
            ),
        )
        self._symbols.append(symbol)
        self._visit_children(
            node,
            VisitContext(owner_qualified_name=qualified_name),
        )


def _parse_tree(source: str) -> Tree:
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))
    if tree.root_node.has_error:
        raise LanguageParseError(
            "failed to parse Python source",
            language=Language.PYTHON,
        )
    return tree


def _get_parser() -> Parser:
    global _PARSER  # noqa: PLW0603
    if _PARSER is None:
        language = TreeSitterLanguage(tree_sitter_python.language())
        _PARSER = Parser(language)
    return _PARSER


def _module_name_for_path(path: Path) -> str:
    package_parts = _package_parts(path.parent)
    if path.name == "__init__.py":
        return ".".join(package_parts) if package_parts else path.parent.name
    return ".".join((*package_parts, path.stem)) if package_parts else path.stem


def _package_parts(directory: Path) -> tuple[str, ...]:
    parts: list[str] = []
    current = directory
    while (current / "__init__.py").exists():
        parts.append(current.name)
        current = current.parent
    return tuple(reversed(parts))


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


def _top_level_statements(node: Node) -> tuple[Node, ...]:
    block = next((child for child in node.children if child.type == "block"), None)
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


def _executable_body_statements(node: Node) -> tuple[Node, ...]:
    return tuple(
        statement
        for statement in _top_level_statements(node)
        if not _is_plain_string_expression_statement(statement)
    )


def _is_plain_string_expression_statement(statement: Node) -> bool:
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

    prefix = python_string_prefix(node_text.decode("utf-8"))
    return "b" not in prefix and "f" not in prefix


def python_string_prefix(literal: str) -> str:
    """Return the lowercase prefix before a Python string literal quote."""
    prefix_chars: list[str] = []
    for character in literal:
        if character in {'"', "'"}:
            break
        prefix_chars.append(character.lower())
    return "".join(prefix_chars)


def _sloc_line_numbers(source: str, tree: Tree) -> frozenset[int]:
    source_lines = source.splitlines(keepends=True)
    text_lines = source.splitlines()
    lines: set[int] = set()
    for token in generate_tokens(iter(source_lines).__next__):
        if token.type not in _IGNORED_SLOC_TOKEN_TYPES:
            lines.add(token.start[0])

    for start, end in _string_ranges(tree.root_node, text_lines):
        for line_no in range(start, end + 1):
            lines.discard(line_no)

    return frozenset(lines)


def _string_ranges(root: Node, source_lines: list[str]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if (
            _is_plain_string_expression_statement(node)
            and (literal := node.named_children[0]) is not None
            and _owns_line(literal, source_lines)
        ):
            ranges.append((literal.start_point[0] + 1, literal.end_point[0] + 1))
        stack.extend(reversed(node.named_children))
    return tuple(ranges)


def _owns_line(literal: Node, source_lines: list[str]) -> bool:
    start_row, start_col = literal.start_point
    end_row, end_col = literal.end_point
    start_line = source_lines[start_row] if start_row < len(source_lines) else ""
    end_line = source_lines[end_row] if end_row < len(source_lines) else ""
    return not start_line[:start_col].strip() and not end_line[end_col:].strip()


def _signature_from_node(node: Node) -> SignatureIR:
    annotations = _arguments_from_node(node)
    return SignatureIR(
        parameters=tuple(annotations),
        annotations=annotations,
        returns=_return_annotation_from_node(node),
    )


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
    return (_text(name_node), _text(type_node) if type_node is not None else None)


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


def _decorator_name(node: Node) -> str:
    raw = _text(node).strip()
    return raw.removeprefix("@").strip()


def _class_base_names(node: Node) -> tuple[str, ...]:
    argument_list = next(
        (child for child in node.children if child.type == "argument_list"),
        None,
    )
    if argument_list is None:
        return ()
    return tuple(_text(child) for child in argument_list.named_children)


def _function_roles(name: str, context: VisitContext) -> frozenset[SymbolRole]:
    roles: set[SymbolRole] = set()
    if _is_dunder_name(name):
        roles.add(SymbolRole.CONTRACT_MEMBER)
    if context.decorators:
        if any(decorator.startswith("property") for decorator in context.decorators):
            roles.add(SymbolRole.COMPUTED_ATTRIBUTE)
        else:
            roles.add(SymbolRole.CONTRACT_MEMBER)
    if (
        context.class_context is not None
        and context.class_context.base_names
        and name not in _RECEIVER_PARAMETER_NAMES
    ):
        roles.add(SymbolRole.INHERITED_OVERRIDE)
    return frozenset(roles)


def _is_dunder_name(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _body_operations(
    file_path: Path,
    node: Node,
    imports: dict[str, str],
) -> tuple[OperationIR, ...]:
    return tuple(
        _operation_from_statement(file_path, statement, imports)
        for statement in _executable_body_statements(node)
    )


def _operation_from_statement(
    file_path: Path,
    statement: Node,
    imports: dict[str, str],
) -> OperationIR:
    kind = _operation_kind(statement)
    return OperationIR(
        kind=kind,
        span=_node_span(file_path, statement),
        value=_operation_value(file_path, statement, imports, kind),
    )


def _operation_kind(statement: Node) -> OperationKind:
    if statement.type in _STATEMENT_OPERATION_KINDS:
        return _STATEMENT_OPERATION_KINDS[statement.type]
    if statement.type == "expression_statement" and statement.named_children:
        expression = statement.named_children[0]
        return _EXPRESSION_OPERATION_KINDS.get(
            expression.type,
            OperationKind.UNKNOWN,
        )
    return OperationKind.UNKNOWN


def _operation_value(
    file_path: Path,
    statement: Node,
    imports: dict[str, str],
    kind: OperationKind,
) -> ValueIR | None:
    if kind is OperationKind.RETURN and statement.named_children:
        return _value_from_node(file_path, statement.named_children[0], imports)
    if kind is OperationKind.CALL:
        return _value_from_node(file_path, statement.named_children[0], imports)
    return None


def _value_from_node(
    file_path: Path,
    node: Node,
    imports: dict[str, str],
) -> ValueIR:
    if node.type == "call":
        return _invocation_value(file_path, node, imports)
    if node.type in {"identifier", "attribute"}:
        return _reference_value(file_path, node, imports)
    if node.type in _LITERAL_TYPES:
        return ValueIR(
            kind=ValueKind.LITERAL,
            span=_node_span(file_path, node),
            text=_text(node),
        )
    if node.type in _COLLECTION_TYPES:
        return _compound_value(file_path, node, imports, ValueKind.COLLECTION)
    if node.type in _OPERATOR_TYPES:
        return _compound_value(file_path, node, imports, ValueKind.OPERATOR)
    return ValueIR(kind=ValueKind.UNKNOWN, span=_node_span(file_path, node), text=_text(node))


def _compound_value(
    file_path: Path,
    node: Node,
    imports: dict[str, str],
    kind: ValueKind,
) -> ValueIR:
    return ValueIR(
        kind=kind,
        span=_node_span(file_path, node),
        text=_text(node),
        arguments=tuple(
            _value_from_node(file_path, child, imports)
            for child in node.named_children
        ),
    )


def _reference_value(
    file_path: Path,
    node: Node,
    imports: dict[str, str],
) -> ValueIR:
    name = _text(node)
    kind = (
        ValueKind.SYMBOL_REFERENCE
        if node.type == "identifier"
        else ValueKind.MEMBER_ACCESS
    )
    return ValueIR(
        kind=kind,
        span=_node_span(file_path, node),
        text=name,
        name=name,
        resolved_name=_resolve_name(name, imports),
    )


def _invocation_value(
    file_path: Path,
    node: Node,
    imports: dict[str, str],
) -> ValueIR:
    raw_name = _call_name(node)
    argument_list = next(
        (child for child in node.children if child.type == "argument_list"),
        None,
    )
    return ValueIR(
        kind=ValueKind.INVOCATION,
        span=_node_span(file_path, node),
        text=_text(node),
        name=raw_name,
        resolved_name=_resolve_name(raw_name, imports) if raw_name is not None else None,
        arguments=(
            tuple(
                _value_from_node(file_path, child, imports)
                for child in argument_list.named_children
            )
            if argument_list is not None
            else ()
        ),
    )


def _symbol_references(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
) -> tuple[ReferenceIR, ...]:
    local = _local_names(node)
    usages = tuple(
        _reference_from_call(call, file_path, imports)
        for call in _iter_nodes(node)
        if call.type == "call"
    )
    return tuple(
        usage
        for usage in usages
        if usage is not None
        and usage.name.split(".", 1)[0] not in local
        and usage.name.split(".", 1)[0] not in _BUILTIN_CALL_ROOTS
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


def _reference_from_call(
    node: Node,
    file_path: Path,
    imports: dict[str, str],
) -> ReferenceIR | None:
    name = _call_name(node)
    if name is None:
        return None
    target = _call_target(node) or node
    return ReferenceIR(
        name=name,
        resolved_name=_resolve_name(name, imports),
        kind="call",
        span=_node_span(file_path, target),
    )


def _call_name(node: Node) -> str | None:
    target = _call_target(node)
    name = None
    if target is not None and target.type in {"identifier", "attribute"}:
        name = _text(target)
    return name


def _call_target(node: Node) -> Node | None:
    return next(
        (
            child
            for child in node.children
            if child.type not in {"argument_list", "(", ")", ","}
        ),
        None,
    )


def _imports_from_root(file_path: Path, root: Node) -> tuple[ImportIR, ...]:
    imports: list[ImportIR] = []
    for child in root.children:
        if child.type == "import_statement":
            imports.extend(_import_statement_names(file_path, child))
        elif child.type == "import_from_statement":
            imports.extend(_import_from_statement_names(file_path, child))
    return tuple(imports)


def _import_statement_names(file_path: Path, node: Node) -> tuple[ImportIR, ...]:
    imports: list[ImportIR] = []
    for child in node.children:
        match child.type:
            case "dotted_name":
                full_name = _text(child)
                imports.append(
                    ImportIR(
                        local_name=full_name.split(".", 1)[0],
                        qualified_name=full_name,
                        span=_node_span(file_path, child),
                    ),
                )
            case "aliased_import":
                if parts := _aliased_import_parts(child):
                    imported, alias = parts
                    imports.append(
                        ImportIR(
                            local_name=alias,
                            qualified_name=imported,
                            span=_node_span(file_path, child),
                        ),
                    )
    return tuple(imports)


def _import_from_statement_names(file_path: Path, node: Node) -> tuple[ImportIR, ...]:
    module = next(
        (child for child in node.children if child.type == "dotted_name"), None,
    )
    module_name = _text(module) if module is not None else ""
    imports: list[ImportIR] = []
    for child in node.children:
        if child is not module:
            _add_import_from_child(imports, file_path, child, module_name)
    return tuple(imports)


def _add_import_from_child(
    imports: list[ImportIR],
    file_path: Path,
    child: Node,
    module_name: str,
) -> None:
    match child.type:
        case "dotted_name":
            imported = _text(child)
            imports.append(
                ImportIR(
                    local_name=imported,
                    qualified_name=(
                        f"{module_name}.{imported}" if module_name else imported
                    ),
                    span=_node_span(file_path, child),
                ),
            )
        case "aliased_import":
            if parts := _aliased_import_parts(child):
                imported, alias = parts
                imports.append(
                    ImportIR(
                        local_name=alias,
                        qualified_name=(
                            f"{module_name}.{imported}" if module_name else imported
                        ),
                        span=_node_span(file_path, child),
                    ),
                )


def _aliased_import_parts(node: Node) -> tuple[str, str] | None:
    names = [
        child
        for child in node.children
        if child.type in {"dotted_name", "identifier"}
    ]
    if len(names) >= _MIN_ALIASED_IMPORT_PARTS:
        return (_text(names[0]), _text(names[-1]))
    return None  # scbc ignore[redundant-return-none] Satisfies explicit optional return.


def _resolve_name(name: str, imports: dict[str, str]) -> str:
    root = name.split(".", 1)[0]
    if root not in imports:
        return name
    return imports[root] if root == name else f"{imports[root]}{name[len(root) :]}"


def _cognitive_for_node(node: Node, *, nesting: int) -> int:
    child_score = sum(
        _cognitive_for_node(child, nesting=nesting) for child in node.children
    )
    if node.type == "boolean_operator":
        return 1 + child_score
    if node.type in _COG_JUMP_TYPES:
        return 1
    if node.type in _COG_FLOW_BREAK_TYPES:
        nested_score = sum(
            _cognitive_for_node(child, nesting=nesting + 1)
            for child in node.children
        )
        return 1 + nesting + nested_score
    return child_score

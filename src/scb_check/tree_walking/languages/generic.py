"""Shared Tree-sitter parser core for minimal multi-language IR."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language as TreeSitterLanguage
from tree_sitter import Parser

from scb_check.tree_walking.artifacts import LanguageParseError
from scb_check.tree_walking.artifacts import ParsedFile
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import ModuleIR
from scb_check.tree_walking.models import SignatureIR
from scb_check.tree_walking.models import SourceSpan
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

_LANGUAGE_NAME_BY_VALUE = {
    Language.CPP: "C++",
    Language.HASKELL: "Haskell",
    Language.JAVASCRIPT: "JavaScript",
    Language.RUST: "Rust",
    Language.TYPESCRIPT: "TypeScript",
    Language.ZIG: "Zig",
}
_IDENTIFIER_NODE_TYPES = frozenset(
    {
        "identifier",
        "field_identifier",
        "property_identifier",
        "type_identifier",
        "variable",
    },
)
_PARAMETER_IDENTIFIER_NODE_TYPES = frozenset({"identifier", "variable", "self"})
_PARAMETER_CONTAINER_NODE_TYPES = frozenset(
    {
        "formal_parameters",
        "parameter_list",
        "parameters",
        "patterns",
    },
)
_ASSIGNMENT_PARENT_NODE_TYPES = frozenset(
    {
        "assignment_expression",
        "init_declarator",
        "lexical_declaration",
        "variable_declaration",
        "variable_declarator",
    },
)
_PUNCTUATION_ONLY_SLOC_CHARS = frozenset("{}[]();,:")
_DEFAULT_BOOLEAN_OPERATOR_TOKENS = frozenset({"&&", "||"})


@dataclass(frozen=True, slots=True)
class TreeSitterLanguageConfig:
    """Configuration for one minimal Tree-sitter language frontend."""

    language: Language
    tree_sitter_language: Callable[[], object]
    function_node_types: frozenset[str]
    class_node_types: frozenset[str] = frozenset()
    owner_context_node_types: frozenset[str] = frozenset()
    anonymous_function_node_types: frozenset[str] = frozenset()
    body_node_types: frozenset[str] = frozenset()
    branch_node_types: frozenset[str] = frozenset()
    loop_node_types: frozenset[str] = frozenset()
    jump_node_types: frozenset[str] = frozenset()
    boolean_expression_node_types: frozenset[str] = frozenset()
    boolean_operator_tokens: frozenset[str] = _DEFAULT_BOOLEAN_OPERATOR_TOKENS
    comment_node_types: frozenset[str] = frozenset({"comment"})
    clone_node_types: frozenset[str] = frozenset()
    identifier_node_types: frozenset[str] = _IDENTIFIER_NODE_TYPES
    literal_node_types: frozenset[str] = frozenset()

    @property
    def display_name(self) -> str:
        """Return a user-facing language name."""
        return _LANGUAGE_NAME_BY_VALUE.get(self.language, self.language.value)

    @property
    def complexity_node_types(self) -> frozenset[str]:
        """Return non-boolean syntax node types that add branch paths."""
        return self.branch_node_types | self.loop_node_types

    @property
    def cognitive_flow_break_node_types(self) -> frozenset[str]:
        """Return syntax node types that add cognitive flow breaks."""
        return self.branch_node_types | self.loop_node_types


@dataclass(frozen=True, slots=True)
class ClassContext:
    """Current class-like owner facts."""

    qualified_name: str
    base_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VisitContext:
    """Current ownership while walking a syntax tree."""

    owner_qualified_name: str | None = None
    class_context: ClassContext | None = None


class GenericTreeSitterParser:
    """Parse one Tree-sitter grammar into minimal language-agnostic IR."""

    def __init__(self, config: TreeSitterLanguageConfig) -> None:
        """Initialize the parser from `config`."""
        self.config = config
        self.language = config.language
        self._parser: Parser | None = None

    def parse(self, file_path: Path, source: str) -> ParsedFile:
        """Parse already-read source text for this language."""
        tree = self._parse_tree(source)
        sloc_lines = _sloc_line_numbers(
            source,
            tree.root_node,
            comment_node_types=self.config.comment_node_types,
        )
        walker = GenericTreeSitterWalker(
            self.config,
            file_path,
            source,
            tree,
            sloc_lines,
        )
        return ParsedFile(
            file=file_path,
            source=source,
            module=walker.module(),
            native_tree=tree,
        )

    def _parse_tree(self, source: str) -> Tree:
        parser = self._get_parser()
        tree = parser.parse(source.encode("utf-8"))
        if tree.root_node.has_error:
            raise LanguageParseError(
                f"failed to parse {self.config.display_name} source",
                language=self.config.language,
            )
        return tree

    def _get_parser(self) -> Parser:
        if self._parser is None:
            language = TreeSitterLanguage(self.config.tree_sitter_language())
            self._parser = Parser(language)
        return self._parser


class GenericTreeSitterWalker:
    """Walk a Tree-sitter tree into minimal module and symbol IR."""

    def __init__(
        self,
        config: TreeSitterLanguageConfig,
        file_path: Path,
        source: str,
        tree: Tree,
        sloc_lines: frozenset[int],
    ) -> None:
        """Initialize with parser config and precomputed SLOC."""
        self._config = config
        self._file_path = file_path
        self._source_lines = source.splitlines()
        self._tree = tree
        self._sloc_lines = sloc_lines
        self._module_name = _module_name_for_path(file_path)
        self._symbols: list[SymbolIR] = []

    def module(self) -> ModuleIR:
        """Return the parsed module IR."""
        self._visit_node(self._tree.root_node, VisitContext(), ())
        return ModuleIR(
            language=self._config.language,
            file=self._file_path,
            module_name=self._module_name,
            span=_module_span(self._file_path, self._source_lines),
            symbols=tuple(self._symbols),
            sloc_lines=self._sloc_lines,
        )

    def _visit_children(
        self,
        node: Node,
        context: VisitContext,
        ancestors: tuple[Node, ...],
    ) -> None:
        for child in node.named_children:
            self._visit_node(child, context, ancestors)

    def _visit_node(
        self,
        node: Node,
        context: VisitContext,
        ancestors: tuple[Node, ...],
    ) -> None:
        node_ancestors = (*ancestors, node)
        if node.type in self._config.class_node_types:
            self._handle_class(node, context, node_ancestors)
            return
        if node.type in self._config.owner_context_node_types:
            self._handle_owner_context(node, context, node_ancestors)
            return
        if node.type in self._config.function_node_types:
            self._handle_function(node, context, ancestors, node_ancestors)
            return
        self._visit_children(node, context, node_ancestors)

    def _handle_class(
        self,
        node: Node,
        context: VisitContext,
        ancestors: tuple[Node, ...],
    ) -> None:
        name = _first_identifier_text(node, self._config.identifier_node_types)
        if name is None:
            self._visit_children(node, context, ancestors)
            return

        qualified_name = _qualified_name(
            self._module_name,
            context.owner_qualified_name,
            name,
        )
        class_symbol = SymbolIR(
            name=name,
            qualified_name=qualified_name,
            kind=SymbolKind.CLASS,
            span=_node_span(self._file_path, node),
            language=self._config.language,
            owner_qualified_name=context.owner_qualified_name,
            sloc=_count_sloc_in_span(node, self._sloc_lines),
        )
        self._symbols.append(class_symbol)
        class_context = ClassContext(qualified_name=qualified_name)
        self._visit_children(
            node,
            VisitContext(
                owner_qualified_name=qualified_name,
                class_context=class_context,
            ),
            ancestors,
        )

    def _handle_owner_context(
        self,
        node: Node,
        context: VisitContext,
        ancestors: tuple[Node, ...],
    ) -> None:
        name = _owner_context_name(node, self._config.identifier_node_types)
        if name is None:
            self._visit_children(node, context, ancestors)
            return
        qualified_name = _qualified_name(
            self._module_name,
            context.owner_qualified_name,
            name,
        )
        self._visit_children(
            node,
            VisitContext(
                owner_qualified_name=qualified_name,
                class_context=ClassContext(qualified_name=qualified_name),
            ),
            ancestors,
        )

    def _handle_function(
        self,
        node: Node,
        context: VisitContext,
        ancestors: tuple[Node, ...],
        node_ancestors: tuple[Node, ...],
    ) -> None:
        name = _function_name(node, ancestors, self._config)
        if name is None:
            self._visit_children(node, context, node_ancestors)
            return

        qualified_name = _qualified_name(
            self._module_name,
            context.owner_qualified_name,
            name,
        )
        kind = (
            SymbolKind.METHOD
            if context.class_context is not None
            else SymbolKind.FUNCTION
        )
        symbol = SymbolIR(
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            span=_node_span(self._file_path, node),
            language=self._config.language,
            signature=SignatureIR(parameters=_parameter_names(node, self._config)),
            owner_qualified_name=context.owner_qualified_name,
            base_names=(
                context.class_context.base_names
                if context.class_context is not None
                else ()
            ),
            sloc=_count_sloc_in_span(node, self._sloc_lines),
            cyc_complexity=1 + _cyclomatic_increment(node, self._config),
            cog_complexity=sum(
                _cognitive_for_node(child, self._config, nesting=0)
                for child in node.children
            ),
        )
        self._symbols.append(symbol)
        self._visit_children(
            node,
            VisitContext(owner_qualified_name=qualified_name),
            node_ancestors,
        )


def _module_span(file_path: Path, source_lines: list[str]) -> SourceSpan:
    if not source_lines:
        return SourceSpan(
            file=file_path,
            start_line=1,
            start_col=0,
            end_line=1,
            end_col=0,
        )
    return SourceSpan(
        file=file_path,
        start_line=1,
        start_col=0,
        end_line=len(source_lines),
        end_col=len(source_lines[-1]),
    )


def _node_span(file_path: Path, node: Node) -> SourceSpan:
    return SourceSpan(
        file=file_path,
        start_line=node.start_point[0] + 1,
        start_col=node.start_point[1],
        end_line=node.end_point[0] + 1,
        end_col=node.end_point[1],
    )


def _qualified_name(
    module_name: str,
    owner_qualified_name: str | None,
    name: str,
) -> str:
    if owner_qualified_name is None:
        return f"{module_name}.{name}"
    return f"{owner_qualified_name}.{name}"


def _module_name_for_path(path: Path) -> str:
    return path.name.removesuffix("".join(path.suffixes)) or path.stem


def _iter_nodes(node: Node) -> tuple[Node, ...]:
    nodes: list[Node] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(current.children))
    return tuple(nodes)


def _text(node: Node) -> str:
    source = node.text or b""
    return source.decode("utf-8")


def _first_identifier_text(
    node: Node,
    identifier_node_types: frozenset[str],
) -> str | None:
    direct = next(
        (
            child
            for child in node.children
            if child.type in identifier_node_types
        ),
        None,
    )
    if direct is not None:
        return _text(direct)

    return next(
        (
            _text(child)
            for child in _iter_nodes(node)
            if child is not node and child.type in identifier_node_types
        ),
        None,
    )


def _function_name(
    node: Node,
    ancestors: tuple[Node, ...],
    config: TreeSitterLanguageConfig,
) -> str | None:
    if node.type not in config.anonymous_function_node_types:
        return _declaration_name(node, config.identifier_node_types)
    return _assigned_name(ancestors, config.identifier_node_types)


def _owner_context_name(
    node: Node,
    identifier_node_types: frozenset[str],
) -> str | None:
    type_node = node.child_by_field_name("type")
    if type_node is not None:
        name = _declaration_name(type_node, identifier_node_types)
        if name is not None:
            return name
    return _first_identifier_text(node, identifier_node_types)


def _declaration_name(
    node: Node,
    identifier_node_types: frozenset[str],
) -> str | None:
    for field_name in ("name", "declarator"):
        child = node.child_by_field_name(field_name)
        if child is None:
            continue
        name = _declaration_name(child, identifier_node_types)
        if name is not None:
            return name

    if node.type in identifier_node_types:
        return _text(node)

    direct = next(
        (
            child
            for child in node.children
            if child.type in identifier_node_types
        ),
        None,
    )
    if direct is not None:
        return _text(direct)

    return next(
        (
            name
            for child in node.named_children
            if (name := _declaration_name(child, identifier_node_types)) is not None
        ),
        None,
    )


def _assigned_name(
    ancestors: tuple[Node, ...],
    identifier_node_types: frozenset[str],
) -> str | None:
    for parent in reversed(ancestors):
        if parent.type not in _ASSIGNMENT_PARENT_NODE_TYPES:
            continue
        name = next(
            (
                _text(child)
                for child in parent.children
                if child.type in identifier_node_types
            ),
            None,
        )
        if name is not None:
            return name
    return None


def _parameter_names(
    node: Node,
    config: TreeSitterLanguageConfig,
) -> tuple[str, ...]:
    container = _first_parameter_container(node, config.body_node_types)
    if container is None:
        return ()
    names = tuple(
        name
        for child in container.named_children
        for name in _parameter_names_from_node(child)
    )
    return tuple(dict.fromkeys(names))


def _first_parameter_container(
    node: Node,
    body_node_types: frozenset[str],
) -> Node | None:
    stack = list(reversed(node.named_children))
    while stack:
        current = stack.pop()
        if current.type in _PARAMETER_CONTAINER_NODE_TYPES:
            return current
        if current.type in body_node_types:
            continue
        stack.extend(reversed(current.named_children))
    return None


def _parameter_names_from_node(node: Node) -> tuple[str, ...]:
    if node.type in _PARAMETER_IDENTIFIER_NODE_TYPES:
        return (_text(node),)
    return tuple(
        _text(child)
        for child in _iter_nodes(node)
        if child.type in _PARAMETER_IDENTIFIER_NODE_TYPES
    )


def _count_sloc_in_span(node: Node, sloc_lines: frozenset[int]) -> int:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return sum(1 for line_no in sloc_lines if start_line <= line_no <= end_line)


def _sloc_line_numbers(
    source: str,
    root: Node,
    *,
    comment_node_types: frozenset[str],
) -> frozenset[int]:
    source_lines = source.splitlines()
    comment_intervals = _comment_intervals_by_line(root, comment_node_types)
    lines: set[int] = set()
    for index, line in enumerate(source_lines, start=1):
        uncommented = _remove_intervals(line, comment_intervals.get(index, ()))
        if uncommented.strip() and not _is_punctuation_only(uncommented):
            lines.add(index)
    return frozenset(lines)


def _comment_intervals_by_line(
    root: Node,
    comment_node_types: frozenset[str],
) -> dict[int, tuple[tuple[int, int], ...]]:
    intervals: defaultdict[int, list[tuple[int, int]]] = defaultdict(list)
    for node in _iter_nodes(root):
        if node.type in comment_node_types:
            _add_comment_intervals(intervals, node)
    return {
        line_no: tuple(sorted(line_intervals))
        for line_no, line_intervals in intervals.items()
    }


def _add_comment_intervals(
    intervals: defaultdict[int, list[tuple[int, int]]],
    node: Node,
) -> None:
    start_row, start_col = node.start_point
    end_row, end_col = node.end_point
    for row in range(start_row, end_row + 1):
        line_no = row + 1
        interval_start = start_col if row == start_row else 0
        interval_end = end_col if row == end_row else 10**9
        intervals[line_no].append((interval_start, interval_end))


def _remove_intervals(line: str, intervals: tuple[tuple[int, int], ...]) -> str:
    if not intervals:
        return line
    parts: list[str] = []
    cursor = 0
    for start, end in intervals:
        bounded_start = max(0, min(start, len(line)))
        bounded_end = max(bounded_start, min(end, len(line)))
        parts.append(line[cursor:bounded_start])
        cursor = max(cursor, bounded_end)
    parts.append(line[cursor:])
    return "".join(parts)


def _is_punctuation_only(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and all(
        character in _PUNCTUATION_ONLY_SLOC_CHARS for character in stripped
    )


def _cyclomatic_increment(node: Node, config: TreeSitterLanguageConfig) -> int:
    return sum(
        1
        for current in _iter_nodes(node)
        if current.type in config.complexity_node_types
        or _is_boolean_operation(current, config)
    )


def _cognitive_for_node(
    node: Node,
    config: TreeSitterLanguageConfig,
    *,
    nesting: int,
) -> int:
    child_score = sum(
        _cognitive_for_node(child, config, nesting=nesting)
        for child in node.children
    )
    if _is_boolean_operation(node, config):
        return 1 + child_score
    if node.type in config.jump_node_types:
        return 1
    if node.type in config.cognitive_flow_break_node_types:
        nested_score = sum(
            _cognitive_for_node(child, config, nesting=nesting + 1)
            for child in node.children
        )
        return 1 + nesting + nested_score
    return child_score


def _is_boolean_operation(node: Node, config: TreeSitterLanguageConfig) -> bool:
    return node.type in config.boolean_expression_node_types and any(
        child.type in config.boolean_operator_tokens
        or (child.text or b"").decode("utf-8") in config.boolean_operator_tokens
        for child in node.children
    )

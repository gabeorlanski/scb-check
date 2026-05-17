"""Detect duplicate syntax subtrees as clone findings."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scb_check.models import CloneBlock
from scb_check.tree_walking.dispatch import ParsedFile
from scb_check.tree_walking.languages.python import python_string_prefix
from scb_check.tree_walking.languages.registry import (
    clone_node_types_for_language,
)
from scb_check.tree_walking.languages.registry import (
    comment_node_types_for_language,
)
from scb_check.tree_walking.languages.registry import (
    identifier_node_types_for_language,
)
from scb_check.tree_walking.languages.registry import (
    literal_node_types_for_language,
)
from scb_check.tree_walking.models import Language

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

CLONE_NODE_TYPES = frozenset(
    {
        "function_definition",
        "if_statement",
        "for_statement",
        "while_statement",
        "with_statement",
        "try_statement",
        "match_statement",
    },
)

_PYTHON_LITERAL_TOKENS = {
    "string": "$STR",
    "string_content": "$STR",
    "f_string": "$STR",
    "string_fragment": "$STR",
    "bytes": "$STR",
    "integer": "$INT",
    "float": "$FLOAT",
    "imaginary": "$FLOAT",
    "true": "$BOOL",
    "false": "$BOOL",
    "none": "$NONE",
}


@dataclass(frozen=True, slots=True)
class _CloneScanContext:
    """Shared inputs for clone candidate extraction."""

    file: Path
    source_lines: tuple[str, ...]
    sloc_lines: frozenset[int]
    min_lines: int
    language: Language


@dataclass(frozen=True, slots=True)
class _NormalizeContext:
    """Shared language facts for clone normalization."""

    language: Language
    identifier_node_types: frozenset[str]
    literal_node_types: frozenset[str]
    comment_node_types: frozenset[str]


@dataclass(frozen=True, slots=True)
class CloneCandidate:
    """Potential duplicate syntax block before group expansion."""

    file: Path
    start_line: int
    end_line: int
    group_hash: str
    first_lines: tuple[str, ...]


def detect_clones(
    files: tuple[ParsedFile, ...],
    min_lines: int = 3,
) -> tuple[CloneBlock, ...]:
    """Return clone blocks found in parsed source `files`."""
    candidates = sorted(
        (
            candidate
            for parsed in files
            if parsed.native_tree is not None
            for candidate in _iter_clone_candidates(
                cast("Tree", parsed.native_tree),
                _CloneScanContext(
                    file=parsed.file,
                    source_lines=tuple(parsed.source.splitlines()),
                    sloc_lines=parsed.module.sloc_lines,
                    min_lines=min_lines,
                    language=parsed.module.language,
                ),
            )
        ),
        key=attrgetter("group_hash"),
    )

    clones: list[CloneBlock] = []
    for hash_value, candidates_iter in groupby(
        candidates,
        key=attrgetter("group_hash"),
    ):
        candidates = tuple(candidates_iter)
        if len(candidates) < 2:  # noqa: PLR2004
            continue

        sorted_candidates = sorted(
            candidates,
            key=lambda candidate: (
                candidate.file.as_posix(),
                candidate.start_line,
                candidate.end_line,
            ),
        )
        instances = tuple(
            (candidate.file, candidate.start_line)
            for candidate in sorted_candidates
        )
        for candidate in sorted_candidates:
            other_instances = tuple(
                instance
                for instance in instances
                if instance != (candidate.file, candidate.start_line)
            )
            clones.append(
                CloneBlock(
                    file=candidate.file,
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    group_hash=hash_value,
                    instance_count=len(sorted_candidates),
                    other_instances=other_instances,
                    first_lines=candidate.first_lines,
                ),
            )

    return tuple(clones)


def _iter_clone_candidates(
    tree: Tree,
    context: _CloneScanContext,
) -> tuple[CloneCandidate, ...]:
    candidates: list[CloneCandidate] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if not _is_potential_clone_block(node, context.language):
            continue
        if (
            clone_candidate := _extract_clone_candidate(
                node,
                context,
            )
        ) is None:
            continue
        candidates.append(clone_candidate)

    return tuple(candidates)


def _is_potential_clone_block(node: Node, language: Language) -> bool:
    return node.type in _clone_node_types(language) and not (
        language is Language.PYTHON and _is_type_checking_block(node)
    )


def _extract_clone_candidate(
    node: Node,
    context: _CloneScanContext,
) -> CloneCandidate | None:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    line_count = sum(
        1 for line in context.sloc_lines if start_line <= line <= end_line
    )
    if line_count < context.min_lines:
        return None

    preview_end_line = min(end_line, start_line + 2)
    return CloneCandidate(
        file=context.file,
        start_line=start_line,
        end_line=end_line,
        group_hash=_hash_ast_subtree(node, context.language),
        first_lines=context.source_lines[start_line - 1 : preview_end_line],
    )


def _is_type_checking_block(node: Node) -> bool:
    condition = node.child_by_field_name("condition")
    text = condition.text if condition is not None else None
    return text in {b"TYPE_CHECKING", b"typing.TYPE_CHECKING"}


def _is_plain_string_statement(node: Node) -> bool:
    if node.type != "expression_statement":
        return False
    if len(node.named_children) != 1:
        return False

    expression = node.named_children[0]
    if expression.type != "string":
        return False

    text = expression.text
    if text is None:
        return False

    prefix = python_string_prefix(text.decode("utf-8"))
    return "b" not in prefix and "f" not in prefix


def _hash_ast_subtree(node: Node, language: Language) -> str:
    normalized = _normalize_ast(node, language)
    return hashlib.md5(
        normalized.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]


def _normalize_ast(node: Node, language: Language) -> str:
    context = _NormalizeContext(
        language=language,
        identifier_node_types=_identifier_node_types(language),
        literal_node_types=_literal_node_types(language),
        comment_node_types=_comment_node_types(language),
    )
    return _normalize_node(node, context, {})


def _normalize_node(
    node: Node,
    context: _NormalizeContext,
    variable_map: dict[str, str],
) -> str:
    if node.type in context.identifier_node_types:
        return _normalized_identifier(node, variable_map)
    if node.type in context.literal_node_types:
        return _literal_token(node.type, context.language)
    if node.type == "operator" and node.text is not None:
        return node.text.decode("utf-8")

    children = _normalizable_children(node, context)
    if not children:
        return node.type

    normalized_children = [
        _normalize_node(child, context, variable_map) for child in children
    ]
    return f"{node.type}({','.join(normalized_children)})"


def _normalized_identifier(node: Node, variable_map: dict[str, str]) -> str:
    if (text := node.text) is None:
        return "$VAR0"
    name = text.decode("utf-8")
    if name not in variable_map:
        variable_map[name] = f"$VAR{len(variable_map) + 1}"
    return variable_map[name]


def _normalizable_children(
    node: Node,
    context: _NormalizeContext,
) -> tuple[Node, ...]:
    return tuple(
        child
        for child in node.children
        if child.type not in context.comment_node_types
        and not (
            context.language is Language.PYTHON
            and _is_plain_string_statement(child)
        )
    )


def _python_or_registry(
    language: Language,
    python_value: frozenset[str],
    registry_getter: Callable[[Language], frozenset[str]],
) -> frozenset[str]:
    if language is Language.PYTHON:
        return python_value
    return registry_getter(language)


def _clone_node_types(language: Language) -> frozenset[str]:
    return _python_or_registry(language, CLONE_NODE_TYPES, clone_node_types_for_language)


def _comment_node_types(language: Language) -> frozenset[str]:
    return _python_or_registry(language, frozenset({"comment"}), comment_node_types_for_language)


def _identifier_node_types(language: Language) -> frozenset[str]:
    return _python_or_registry(language, frozenset({"identifier"}), identifier_node_types_for_language)


def _literal_node_types(language: Language) -> frozenset[str]:
    return _python_or_registry(language, frozenset(_PYTHON_LITERAL_TOKENS), literal_node_types_for_language)


def _literal_token(node_type: str, language: Language) -> str:
    if language is Language.PYTHON:
        return _PYTHON_LITERAL_TOKENS[node_type]
    if "string" in node_type or "char" in node_type:
        return "$STR"
    if "float" in node_type:
        return "$FLOAT"
    if "bool" in node_type or node_type in {"false", "true"}:
        return "$BOOL"
    if "null" in node_type or node_type in {"none", "undefined"}:
        return "$NONE"
    return "$LIT"

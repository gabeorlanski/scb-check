"""Detect duplicate Python syntax subtrees as clone findings."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scb_check.models import CloneBlock
from scb_check.tree_walking.dispatch import ParsedFile
from scb_check.tree_walking.languages.python import python_string_prefix

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

_LITERAL_TOKENS = {
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
    """Return clone blocks found in parsed Python `files`."""
    candidates = sorted(
        (
            candidate
            for parsed in files
            if parsed.native_tree is not None
            for candidate in _iter_clone_candidates(
                parsed.file,
                parsed.source,
                cast("Tree", parsed.native_tree),
                parsed.module.sloc_lines,
                min_lines,
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
    file_path: Path,
    source: str,
    tree: Tree,
    sloc_lines: frozenset[int],
    min_lines: int,
) -> tuple[CloneCandidate, ...]:
    source_lines = source.splitlines()
    candidates: list[CloneCandidate] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if not _is_potential_clone_block(node):
            continue
        if (
            clone_candidate := _extract_clone_candidate(
                file_path,
                source_lines,
                node,
                sloc_lines,
                min_lines=min_lines,
            )
        ) is None:
            continue
        candidates.append(clone_candidate)

    return tuple(candidates)


def _is_potential_clone_block(node: Node) -> bool:
    return node.type in CLONE_NODE_TYPES and not _is_type_checking_block(node)


def _extract_clone_candidate(
    file_path: Path,
    source_lines: list[str],
    node: Node,
    sloc_lines: frozenset[int],
    *,
    min_lines: int,
) -> CloneCandidate | None:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    line_count = sum(1 for line in sloc_lines if start_line <= line <= end_line)
    if line_count < min_lines:
        return None

    preview_end_line = min(end_line, start_line + 2)
    return CloneCandidate(
        file=file_path,
        start_line=start_line,
        end_line=end_line,
        group_hash=_hash_ast_subtree(node),
        first_lines=tuple(source_lines[start_line - 1 : preview_end_line]),
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


def _hash_ast_subtree(node: Node) -> str:
    normalized = _normalize_ast(node)
    return hashlib.md5(
        normalized.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]


def _normalize_ast(node: Node) -> str:
    variable_map: dict[str, str] = {}
    variable_counter = 0

    def normalize(current: Node) -> str:
        nonlocal variable_counter

        if current.type == "identifier":
            if (text := current.text) is None:
                return "$VAR0"
            name = text.decode("utf-8")
            if name not in variable_map:
                variable_counter += 1
                variable_map[name] = f"$VAR{variable_counter}"
            return variable_map[name]

        if current.type in _LITERAL_TOKENS:
            return _LITERAL_TOKENS[current.type]

        children = tuple(
            child
            for child in current.children
            if child.type != "comment" and not _is_plain_string_statement(child)
        )
        if not children:
            return current.type

        normalized_children = [normalize(child) for child in children]
        return f"{current.type}({','.join(normalized_children)})"

    return normalize(node)

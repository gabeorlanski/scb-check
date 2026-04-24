from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scb_check.models import CloneBlock

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
    }
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
class _CloneCandidate:
    file: Path
    start_line: int
    end_line: int
    group_hash: str
    first_lines: tuple[str, ...]


def detect_clones(
    files: tuple[tuple[Path, str, Tree], ...],
    min_lines: int = 3,
) -> tuple[CloneBlock, ...]:
    """Find duplicated AST blocks across ``files``.

    Only node types in ``CLONE_NODE_TYPES`` (function defs, loops, ``if``,
    ``try``, ``with``, ``match``) spanning at least ``min_lines`` lines are
    considered. Identifiers and literals are normalized before hashing so
    blocks that differ only in variable names or literal values still
    collide. A group must contain at least two instances to be emitted;
    each instance is returned as its own ``CloneBlock`` sharing a
    ``group_hash``.
    """

    groups: defaultdict[str, list[_CloneCandidate]] = defaultdict(list)
    for file_path, source, tree in files:
        for candidate in _iter_clone_candidates(
            file_path,
            source,
            tree,
            min_lines,
        ):
            groups[candidate.group_hash].append(candidate)

    clones: list[CloneBlock] = []
    for hash_value, candidates in sorted(groups.items()):
        if len(candidates) < 2:
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
                )
            )

    return tuple(clones)


def _iter_clone_candidates(
    file_path: Path,
    source: str,
    tree: Tree,
    min_lines: int,
) -> tuple[_CloneCandidate, ...]:
    source_lines = source.splitlines()
    candidates: list[_CloneCandidate] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        if node.type in CLONE_NODE_TYPES:
            line_count = node.end_point[0] - node.start_point[0] + 1
            if line_count >= min_lines:
                hash_value = _hash_ast_subtree(node)
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                preview_end_line = min(end_line, start_line + 2)
                candidates.append(
                    _CloneCandidate(
                        file=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        group_hash=hash_value,
                        first_lines=tuple(
                            source_lines[start_line - 1 : preview_end_line]
                        ),
                    )
                )
        stack.extend(node.children)

    return tuple(candidates)


def _hash_ast_subtree(node: Node) -> str:
    normalized = _normalize_ast(node)
    return hashlib.md5(
        normalized.encode("utf-8"), usedforsecurity=False
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
            child for child in current.children if child.type != "comment"
        )
        if not children:
            return current.type

        normalized_children = [normalize(child) for child in children]
        return f"{current.type}({','.join(normalized_children)})"

    return normalize(node)

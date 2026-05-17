"""Pure Tree-sitter `Node` utilities shared by language walkers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scb_check.tree_walking.models import SourceSpan

if TYPE_CHECKING:
    from pathlib import Path

    from tree_sitter import Node


def module_span(file_path: Path, source_lines: list[str]) -> SourceSpan:
    """Return a `SourceSpan` covering an entire module's source text."""
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


def node_span(file_path: Path, node: Node) -> SourceSpan:
    """Return a 1-indexed `SourceSpan` for a Tree-sitter `Node`."""
    return SourceSpan(
        file=file_path,
        start_line=node.start_point[0] + 1,
        start_col=node.start_point[1],
        end_line=node.end_point[0] + 1,
        end_col=node.end_point[1],
    )


def qualified_name(
    module_name: str,
    owner_qualified_name: str | None,
    name: str,
) -> str:
    """Join a symbol's owner and `name` into a dotted qualified name."""
    if owner_qualified_name is None:
        return f"{module_name}.{name}"
    return f"{owner_qualified_name}.{name}"


def iter_nodes(node: Node) -> tuple[Node, ...]:
    """Pre-order flatten a Tree-sitter subtree into a tuple of nodes."""
    nodes: list[Node] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(current.children))
    return tuple(nodes)


def text(node: Node) -> str:
    """Return UTF-8 decoded source text for `node`."""
    source = node.text or b""
    return source.decode("utf-8")


def count_sloc_in_span(node: Node, sloc_lines: frozenset[int]) -> int:
    """Count `sloc_lines` falling within the 1-indexed span of `node`."""
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return sum(1 for line_no in sloc_lines if start_line <= line_no <= end_line)

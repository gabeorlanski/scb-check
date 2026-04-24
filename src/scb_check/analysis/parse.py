from __future__ import annotations

from pathlib import Path

import tree_sitter_python
from tree_sitter import Language
from tree_sitter import Parser
from tree_sitter import Tree

from scb_check.logging import get_logger

logger = get_logger(__name__)


class ParseError(ValueError):  # scbc ignore[empty-exception-subclass]
    pass


_PARSER: Parser | None = None


def parse_file(file_path: Path) -> tuple[str, Tree]:
    """Read ``file_path`` and parse it with the shared tree-sitter parser.

    Returns ``(source, tree)``. Raises ``ParseError`` if the file cannot
    be read or if tree-sitter reports a syntax error — callers
    (the pipeline) catch this and skip the file with a warning.
    """

    try:
        source = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "file is not valid UTF-8, reading with replacement characters",
            file=str(file_path),
        )
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError(f"failed to read Python file: {file_path}") from exc

    try:
        tree = parse_source(source)
    except ParseError as exc:
        raise ParseError(f"failed to parse Python file: {file_path}") from exc

    return source, tree


def parse_source(source: str) -> Tree:
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))
    if tree.root_node.has_error:
        raise ParseError("failed to parse Python source")
    return tree


def _get_parser() -> Parser:
    global _PARSER
    if _PARSER is None:
        language = Language(tree_sitter_python.language())
        _PARSER = Parser(language)
    return _PARSER

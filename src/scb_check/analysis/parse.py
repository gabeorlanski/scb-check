from __future__ import annotations

from pathlib import Path

import tree_sitter_python
from tree_sitter import Language
from tree_sitter import Parser
from tree_sitter import Tree


class ParseError(ValueError):
    pass


_PARSER: Parser | None = None


def parse_file(file_path: Path) -> tuple[str, Tree]:
    try:
        source = file_path.read_text(encoding="utf-8")
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

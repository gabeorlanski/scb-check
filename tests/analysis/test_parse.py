from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES

from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_file


def test_parse_returns_source_and_tree() -> None:
    """Valid Python files return decoded source and a module tree."""
    source_path = FIXTURES / "corpus" / "module_a.py"

    source, tree = parse_file(source_path)

    assert "def first" in source
    assert tree.root_node.type == "module"


def test_parse_rejects_invalid_syntax() -> None:
    """Invalid Python syntax raises ParseError."""
    source_path = FIXTURES / "invalid.py"

    with pytest.raises(ParseError, match="failed to parse Python file"):
        parse_file(source_path)


def test_parse_replaces_invalid_utf8(tmp_path: Path) -> None:
    """Invalid UTF-8 bytes are decoded with replacement characters."""
    source_path = tmp_path / "weird.py"
    source_path.write_bytes(b"x = b'\\xff'\n")

    source, tree = parse_file(source_path)

    assert "x" in source
    assert tree.root_node.type == "module"


def test_parse_rejects_missing_file(tmp_path: Path) -> None:
    """Missing files raise ParseError with a read failure."""
    with pytest.raises(ParseError, match="failed to read Python file"):
        parse_file(tmp_path / "missing.py")

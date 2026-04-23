from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES

from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_file


def test_parse_file_returns_source_and_tree() -> None:
    source_path = FIXTURES / "corpus" / "module_a.py"

    source, tree = parse_file(source_path)

    assert "def first" in source
    assert tree.root_node.type == "module"


def test_parse_file_raises_for_syntax_error() -> None:
    source_path = FIXTURES / "invalid.py"

    with pytest.raises(ParseError, match="failed to parse Python file"):
        parse_file(source_path)


def test_parse_file_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="failed to read Python file"):
        parse_file(tmp_path / "missing.py")

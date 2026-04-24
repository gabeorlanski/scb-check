from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES

from scb_check.analysis.parse import ParseError
from scb_check.analysis.parse import parse_file


def test_01() -> None:
    source_path = FIXTURES / "corpus" / "module_a.py"

    source, tree = parse_file(source_path)

    assert "def first" in source
    assert tree.root_node.type == "module"


def test_02() -> None:
    source_path = FIXTURES / "invalid.py"

    with pytest.raises(ParseError, match="failed to parse Python file"):
        parse_file(source_path)


def test_03(tmp_path: Path) -> None:
    source_path = tmp_path / "weird.py"
    source_path.write_bytes(b"x = b'\\xff'\n")

    source, tree = parse_file(source_path)

    assert "x" in source
    assert tree.root_node.type == "module"


def test_04(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="failed to read Python file"):
        parse_file(tmp_path / "missing.py")

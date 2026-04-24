from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from conftest import FIXTURES

from scb_check.analysis.loc import sloc_line_numbers
from scb_check.analysis.parse import parse_file
from scb_check.analysis.symbols import extract_functions


def test_01() -> None:
    source_path = FIXTURES / "symbols_sample.py"
    source, tree = parse_file(source_path)

    symbols = extract_functions(
        source_path, tree, sloc_line_numbers(source, tree)
    )
    names = {symbol.name for symbol in symbols}

    assert names == {"format_name", "outer", "inner"}


def test_02() -> None:
    source_path = FIXTURES / "corpus" / "module_b.py"
    source, tree = parse_file(source_path)

    symbols = extract_functions(
        source_path, tree, sloc_line_numbers(source, tree)
    )
    complex_symbol = next(
        symbol for symbol in symbols if symbol.name == "complex_route"
    )

    assert complex_symbol.complexity > 10
    assert complex_symbol.sloc > 0


def test_03(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.py"
    source_path.write_text(
        dedent(
            '''
            def marker():
                value = 1
                """not a real docstring, but radon treats it as non-sloc"""
                return value
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    source, tree = parse_file(source_path)

    symbols = extract_functions(
        source_path,
        tree,
        frozenset({1, 2, 4}),
    )

    assert source
    assert symbols[0].sloc == 3

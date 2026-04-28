from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from conftest import FIXTURES

from scb_check.analysis.loc import sloc_line_numbers
from scb_check.analysis.parse import parse_file
from scb_check.analysis.symbols import extract_functions


def test_extracts_nested_functions() -> None:
    """Function extraction includes nested definitions."""
    source_path = FIXTURES / "symbols_sample.py"
    source, tree = parse_file(source_path)

    symbols = extract_functions(
        source_path,
        tree,
        sloc_line_numbers(source, tree),
    )
    names = {symbol.name for symbol in symbols}

    assert names == {"format_name", "outer", "inner"}


def test_reports_complexity_and_sloc() -> None:
    """Extracted functions include complexity and SLOC metrics."""
    source_path = FIXTURES / "corpus" / "module_b.py"
    source, tree = parse_file(source_path)

    symbols = extract_functions(
        source_path,
        tree,
        sloc_line_numbers(source, tree),
    )
    complex_symbol = next(
        symbol for symbol in symbols if symbol.name == "complex_route"
    )

    assert complex_symbol.cyc_complexity > 10
    assert complex_symbol.sloc > 0


def test_uses_supplied_sloc_lines(tmp_path: Path) -> None:
    """Function SLOC is counted from the supplied SLOC line set."""
    source_path = tmp_path / "sample.py"
    source_path.write_text(
        dedent(
            '''
            def marker():
                value = 1
                """not a real docstring, but radon treats it as non-sloc"""
                return value
            ''',
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


def test_builds_symbol_ir(tmp_path: Path) -> None:
    """Function extraction emits the ParsedSymbol IR fields."""
    source_path = tmp_path / "sample.py"
    source_path.write_text(
        dedent(
            """
            import os
            from package.tools import make as mk, Widget

            def route(value: int, fallback=None) -> str:
                if value and fallback:
                    return mk(value)
                return os.path.join(str(value), Widget())
            """,
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    source, tree = parse_file(source_path)

    symbol = extract_functions(
        source_path, tree, sloc_line_numbers(source, tree)
    )[0]

    assert {
        "name": symbol.name,
        "file": symbol.file,
        "start": symbol.start,
        "end": symbol.end,
        "node_type": symbol.node_type,
        "statements": symbol.statements,
        "sloc": symbol.sloc,
        "cyc_complexity": symbol.cyc_complexity,
        "cog_complexity": symbol.cog_complexity,
        "agruments": symbol.agruments,
        "arguments": symbol.arguments,
        "returns": symbol.returns,
        "usages": tuple(
            (usage.line, usage.col, usage.name, usage.resolved_name, usage.kind)
            for usage in symbol.usages
        ),
    } == {
        "name": "route",
        "file": source_path,
        "start": (4, 0),
        "end": (7, 45),
        "node_type": "function_definition",
        "statements": 2,
        "sloc": 4,
        "cyc_complexity": 3,
        "cog_complexity": 2,
        "agruments": {"value": "int", "fallback": None},
        "arguments": {"value": "int", "fallback": None},
        "returns": "str",
        "usages": (
            (6, 15, "mk", "package.tools.make", "call"),
            (7, 11, "os.path.join", "os.path.join", "call"),
            (7, 36, "Widget", "package.tools.Widget", "call"),
        ),
    }


def test_complexity_counts_nesting(tmp_path: Path) -> None:
    """Cognitive complexity adds one point per nesting level."""
    source_path = tmp_path / "sample.py"
    source_path.write_text(
        dedent(
            """
            def nested(items):
                for item in items:
                    if item:
                        while item.ready:
                            break
            """,
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    source, tree = parse_file(source_path)

    symbol = extract_functions(
        source_path, tree, sloc_line_numbers(source, tree)
    )[0]

    assert symbol.cog_complexity == 7

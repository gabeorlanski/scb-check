from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.analysis.clones import detect_clones
from scb_check.pipeline import analyze_files
from scb_check.tree_walking.dispatch import parse_source_file
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import SymbolKind

_LANGUAGE_SAMPLES = {
    Language.RUST: (
        "sample.rs",
        "compute",
        """
        fn compute(value: i32) -> i32 {
            let mut total = 0;
            if value > 0 {
                for item in 0..value {
                    total += item;
                }
            }
            total
        }
        """,
    ),
    Language.JAVASCRIPT: (
        "sample.js",
        "compute",
        """
        function compute(value) {
          let total = 0;
          if (value > 0) {
            for (const item of values) {
              total += item;
            }
          }
          return total;
        }
        """,
    ),
    Language.TYPESCRIPT: (
        "sample.ts",
        "compute",
        """
        function compute(value: number): number {
          let total = 0;
          if (value > 0) {
            for (const item of values) {
              total += item;
            }
          }
          return total;
        }
        """,
    ),
    Language.ZIG: (
        "sample.zig",
        "compute",
        """
        pub fn compute(value: i32) i32 {
            var total: i32 = 0;
            if (value > 0) {
                for (items) |item| {
                    total += item;
                }
            }
            return total;
        }
        """,
    ),
    Language.HASKELL: (
        "Sample.hs",
        "compute",
        """
        module Sample where

        compute value =
          if value > 0 then
            case value of
              1 -> value
              _ -> value + 1
          else
            0
        """,
    ),
    Language.CPP: (
        "sample.cpp",
        "compute",
        """
        int compute(int value) {
          int total = 0;
          if (value > 0) {
            for (auto item : values) {
              total += item;
            }
          }
          return total;
        }
        """,
    ),
}


@pytest.mark.parametrize("language", tuple(_LANGUAGE_SAMPLES))
def test_new_languages_emit_complexity_symbols(
    tmp_path: Path,
    language: Language,
) -> None:
    """Each new parser emits function symbols with computed complexity."""
    name, function_name, source = _LANGUAGE_SAMPLES[language]
    source_file = _write_source(tmp_path, name, source)

    module = parse_source_file(source_file, source_file.read_text(encoding="utf-8")).module

    assert module.language is language
    function = next(symbol for symbol in module.symbols if symbol.name == function_name)
    assert function.kind is SymbolKind.FUNCTION
    assert function.sloc > 0
    assert function.cyc_complexity > 1
    assert function.cog_complexity > 0


def test_cpp_declarator_names_function(tmp_path: Path) -> None:
    """C++ function names come from declarators, not return types."""
    source_file = _write_source(
        tmp_path,
        "widget.cpp",
        """
        Widget build(Foo value) {
          return Widget{};
        }
        """,
    )

    module = parse_source_file(source_file, source_file.read_text(encoding="utf-8")).module

    assert [
        (symbol.name, symbol.qualified_name, symbol.kind)
        for symbol in module.symbols
    ] == [("build", "widget.build", SymbolKind.FUNCTION)]


def test_rust_trait_impl_owns_method(tmp_path: Path) -> None:
    """Rust trait impl methods are owned by the implemented type."""
    source_file = _write_source(
        tmp_path,
        "widget.rs",
        """
        impl Display for Foo {
            fn render(&self) -> i32 {
                1
            }
        }
        """,
    )

    module = parse_source_file(source_file, source_file.read_text(encoding="utf-8")).module

    method = next(symbol for symbol in module.symbols if symbol.name == "render")
    assert method.kind is SymbolKind.METHOD
    assert method.owner_qualified_name == "widget.Foo"
    assert method.qualified_name == "widget.Foo.render"


def test_duplicate_basenames_scored(tmp_path: Path) -> None:
    """Same-named generic functions in duplicate basenames remain distinct."""
    first = _write_source(
        tmp_path,
        "api/index.js",
        """
        function handler(value) {
          return value + 1;
        }
        """,
    )
    second = _write_source(
        tmp_path,
        "workers/index.js",
        """
        function handler(value) {
          return value + 2;
        }
        """,
    )

    result = analyze_files((first, second), disable_sg=True)
    functions = result.flags.findings.all_functions

    assert len(functions) == 2
    assert {function.file.parent.name for function in functions} == {"api", "workers"}
    assert len({function.qualified_name for function in functions}) == 2


def test_cpp_overloads_scored(tmp_path: Path) -> None:
    """C++ overloads remain distinct in project function metrics."""
    source_file = _write_source(
        tmp_path,
        "overloads.cpp",
        """
        int parse(int value) {
          return value + 1;
        }

        double parse(double value) {
          return value + 1.0;
        }
        """,
    )

    result = analyze_files((source_file,), disable_sg=True)
    functions = result.flags.findings.all_functions

    assert len(functions) == 2
    assert {function.start_line for function in functions} == {1, 5}
    assert len({function.qualified_name for function in functions}) == 2


def test_haskell_haddock_excluded_from_sloc(tmp_path: Path) -> None:
    """Haddock-only lines are excluded from Haskell `SLOC`."""
    source_file = _write_source(
        tmp_path,
        "Sample.hs",
        """
        module Sample where

        -- | Compute the next value.
        compute value =
          value + 1
        """,
    )

    module = parse_source_file(source_file, source_file.read_text(encoding="utf-8")).module

    assert module.sloc_lines == frozenset({1, 4, 5})


@pytest.mark.parametrize(
    ("language", "name", "source"),
    [
        (
            Language.JAVASCRIPT,
            "sample.js",
            """
            function* gen(values) {
              for (const value of values) {
                yield value;
              }
            }

            const make = function* (values) {
              yield values[0];
            };
            """,
        ),
        (
            Language.TYPESCRIPT,
            "sample.ts",
            """
            function* gen(values: number[]): Generator<number> {
              for (const value of values) {
                yield value;
              }
            }

            const make = function* (values: number[]) {
              yield values[0];
            };
            """,
        ),
    ],
)
def test_generator_functions_emit_symbols(
    tmp_path: Path,
    language: Language,
    name: str,
    source: str,
) -> None:
    """JavaScript-family generator functions become function symbols."""
    source_file = _write_source(tmp_path, name, source)

    module = parse_source_file(source_file, source_file.read_text(encoding="utf-8")).module

    assert module.language is language
    assert {
        symbol.name
        for symbol in module.symbols
        if symbol.kind is SymbolKind.FUNCTION
    } == {"gen", "make"}


_CLONE_SOURCES = {
    Language.RUST: (
        "sample.rs",
        """
        fn first(value: i32) -> i32 {
            let current = value + 1;
            let doubled = current * 2;
            doubled
        }

        fn second(value: i32) -> i32 {
            let current = value + 2;
            let doubled = current * 2;
            doubled
        }
        """,
    ),
    Language.JAVASCRIPT: (
        "sample.js",
        """
        function first(value) {
          const current = value + 1;
          const doubled = current * 2;
          return doubled;
        }

        function second(value) {
          const current = value + 2;
          const doubled = current * 2;
          return doubled;
        }
        """,
    ),
    Language.TYPESCRIPT: (
        "sample.ts",
        """
        function first(value: number): number {
          const current = value + 1;
          const doubled = current * 2;
          return doubled;
        }

        function second(value: number): number {
          const current = value + 2;
          const doubled = current * 2;
          return doubled;
        }
        """,
    ),
    Language.ZIG: (
        "sample.zig",
        """
        fn first(value: i32) i32 {
            const current = value + 1;
            const doubled = current * 2;
            return doubled;
        }

        fn second(value: i32) i32 {
            const current = value + 2;
            const doubled = current * 2;
            return doubled;
        }
        """,
    ),
    Language.HASKELL: (
        "Sample.hs",
        """
        first value =
          let current = value + 1
              doubled = current * 2
          in doubled

        second value =
          let current = value + 2
              doubled = current * 2
          in doubled
        """,
    ),
    Language.CPP: (
        "sample.cpp",
        """
        int first(int value) {
          int current = value + 1;
          int doubled = current * 2;
          return doubled;
        }

        int second(int value) {
          int current = value + 2;
          int doubled = current * 2;
          return doubled;
        }
        """,
    ),
}


@pytest.mark.parametrize("language", tuple(_CLONE_SOURCES))
def test_new_languages_detect_clones(
    tmp_path: Path,
    language: Language,
) -> None:
    """Duplicate function bodies are clone candidates in each new language."""
    name, source = _CLONE_SOURCES[language]
    source_file = _write_source(tmp_path, name, source)
    parsed = parse_source_file(source_file, source_file.read_text(encoding="utf-8"))

    clones = detect_clones((parsed,))

    assert len(clones) == 2
    assert {clone.instance_count for clone in clones} == {2}


@pytest.mark.parametrize(
    ("name", "source"),
    [
        (
            "sample.js",
            """
            function* first(values) {
              const current = values[0];
              yield current + 1;
              yield current + 2;
            }

            function* second(values) {
              const current = values[1];
              yield current + 1;
              yield current + 2;
            }
            """,
        ),
        (
            "sample.ts",
            """
            function* first(values: number[]) {
              const current = values[0];
              yield current + 1;
              yield current + 2;
            }

            function* second(values: number[]) {
              const current = values[1];
              yield current + 1;
              yield current + 2;
            }
            """,
        ),
    ],
)
def test_generator_functions_detect_clones(
    tmp_path: Path,
    name: str,
    source: str,
) -> None:
    """JavaScript-family generator bodies participate in clone detection."""
    source_file = _write_source(tmp_path, name, source)
    parsed = parse_source_file(source_file, source_file.read_text(encoding="utf-8"))

    clones = detect_clones((parsed,))

    assert len(clones) == 2
    assert {clone.instance_count for clone in clones} == {2}


def _write_source(tmp_path: Path, name: str, source: str) -> Path:
    destination = tmp_path / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dedent(source).strip() + "\n", encoding="utf-8")
    return destination.resolve()

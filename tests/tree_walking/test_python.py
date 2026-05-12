from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.tree_walking.dispatch import LanguageParseError
from scb_check.tree_walking.languages.python import PythonParser
from scb_check.tree_walking.models import OperationKind
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.models import SymbolRole
from scb_check.tree_walking.models import ValueKind


def test_python_parser_builds_module_ir(tmp_path: Path) -> None:
    """Python parsing emits language-agnostic module and symbol facts."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        import os
        from package.tools import make as mk, Widget

        class Resource(BaseResource):
            @property
            def identifier(self):
                return self._identifier

        def route(value: int, fallback=None) -> str:
            if value and fallback:
                return mk(value)
            return os.path.join(str(value), Widget())
        """,
    ).strip() + "\n"

    module = PythonParser().parse(file_path, source).module

    assert module.sloc_lines == frozenset({1, 2, 4, 5, 6, 7, 9, 10, 11, 12})
    assert tuple(import_.local_name for import_ in module.imports) == (
        "os",
        "mk",
        "Widget",
    )
    route = next(symbol for symbol in module.symbols if symbol.name == "route")
    assert {
        "kind": route.kind,
        "qualified_name": route.qualified_name,
        "start": route.span.start_line,
        "end": route.span.end_line,
        "parameters": tuple(route.signature.parameters),
        "returns": route.signature.returns,
        "sloc": route.sloc,
        "cyc_complexity": route.cyc_complexity,
        "cog_complexity": route.cog_complexity,
        "references": tuple(
            (reference.name, reference.resolved_name, reference.kind)
            for reference in route.references
        ),
    } == {
        "kind": SymbolKind.FUNCTION,
        "qualified_name": "sample.route",
        "start": 9,
        "end": 12,
        "parameters": ("value", "fallback"),
        "returns": "str",
        "sloc": 4,
        "cyc_complexity": 3,
        "cog_complexity": 2,
        "references": (
            ("mk", "package.tools.make", "call"),
            ("os.path.join", "os.path.join", "call"),
            ("Widget", "package.tools.Widget", "call"),
        ),
    }
    returned = route.return_operations[0]
    assert returned.kind is OperationKind.RETURN
    assert returned.value is not None
    assert returned.value.kind is ValueKind.INVOCATION


def test_python_parser_marks_required_api_roles(tmp_path: Path) -> None:
    """Decorators, dunders, and inherited methods become semantic roles."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        class Resource:
            @property
            def identifier(self):
                return self._identifier

            def __str__(self):
                return self.identifier

        class Encoder(BaseEncoder):
            def default(self, value):
                return value
        """,
    ).strip() + "\n"

    module = PythonParser().parse(file_path, source).module
    roles_by_name = {symbol.qualified_name: symbol.roles for symbol in module.symbols}

    assert SymbolRole.COMPUTED_ATTRIBUTE in roles_by_name["sample.Resource.identifier"]
    assert SymbolRole.CONTRACT_MEMBER in roles_by_name["sample.Resource.__str__"]
    assert SymbolRole.INHERITED_OVERRIDE in roles_by_name["sample.Encoder.default"]


def test_python_parser_rejects_syntax_errors(tmp_path: Path) -> None:
    """Syntax errors are parser failures, not partial IR."""
    file_path = tmp_path / "broken.py"

    with pytest.raises(LanguageParseError, match="failed to parse Python source"):
        PythonParser().parse(file_path, "def broken(:\n    return 1\n")

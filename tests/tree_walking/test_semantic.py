from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from scb_check.tree_walking.languages.python import PythonParser
from scb_check.tree_walking.models import EffectKind
from scb_check.tree_walking.semantic import RuleContext
from scb_check.tree_walking.semantic import build_project


def test_project_context_derives_effects_and_project_calls(tmp_path: Path) -> None:
    """Semantic context resolves project calls and external call effects."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        import json

        def normalize(value):
            if value:
                return value.strip()
            return ""

        def clean(value):
            return normalize(value)

        def parse_payload(value):
            return json.loads(value)
        """,
    ).strip() + "\n"
    module = PythonParser().parse(file_path, source).module
    project = build_project((module,))
    context = RuleContext(project)

    clean = project.symbols_by_qualified_name["sample.clean"]
    parse_payload = project.symbols_by_qualified_name["sample.parse_payload"]

    assert context.returned_project_call_forwards_parameters(clean)
    assert EffectKind.PROJECT_CALL in {
        effect.kind for effect in context.effects_for_symbol(clean)
    }
    assert EffectKind.EXTERNAL_CALL in {
        effect.kind for effect in context.effects_for_symbol(parse_payload)
    }
    assert context.return_has_meaningful_effects(parse_payload)


def test_project_context_identifies_required_api_surfaces(tmp_path: Path) -> None:
    """Keep reasons are queried through semantic context, not syntax."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        class Encoder(BaseEncoder):
            def default(self, value):
                return value
        """,
    ).strip() + "\n"
    module = PythonParser().parse(file_path, source).module
    project = build_project((module,))
    context = RuleContext(project)

    symbol = project.symbols_by_qualified_name["sample.Encoder.default"]

    assert context.is_required_api_surface(symbol)
    assert context.is_inherited_override(symbol)

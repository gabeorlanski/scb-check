from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.rules.low_use_short_function import LowUseShortFunctionRule
from scb_check.rules.low_use_short_function import LowUseShortFunctionSettings
from scb_check.rules.runner import run_rules
from scb_check.tree_walking.languages.python import PythonParser
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.semantic import build_project


def test_low_use_short_function_flags_inlineable_helpers(tmp_path: Path) -> None:
    """A short helper used once is reported when inlining stays within budgets."""
    source = """
        def clean(value):
            normalized = value.strip()
            return normalized

        def route(value):
            return clean(value)
    """

    findings = _run_rule(tmp_path, source)

    assert tuple(finding.subject_name for finding in findings) == ("clean",)
    assert findings[0].rule_id == "low-use-short-function"


@pytest.mark.parametrize(
    ("source", "settings"),
    [
        pytest.param(
            """
            def clean(value):
                normalized = value.strip()
                labeled = f"<{normalized}>"
                return labeled

            def route(value):
                return clean(value)
            """,
            LowUseShortFunctionSettings(
                enabled=True,
                max_inline_caller_sloc=4,
            ),
            id="line-budget",
        ),
        pytest.param(
            """
            def choose(value):
                if value:
                    return value
                return ""

            def route(value):
                return choose(value)
            """,
            LowUseShortFunctionSettings(
                enabled=True,
                max_inline_caller_complexity=1,
            ),
            id="cyclomatic-budget",
        ),
        pytest.param(
            """
            def choose(value):
                if value:
                    return value
                return ""

            def route(value):
                return choose(value)
            """,
            LowUseShortFunctionSettings(
                enabled=True,
                max_inline_caller_cognitive_complexity=0,
            ),
            id="cognitive-budget",
        ),
        pytest.param(
            """
            def choose(value):
                if value:
                    return value
                return ""

            def route(value):
                if value is not None:
                    if value:
                        return choose(value)
                return ""
            """,
            LowUseShortFunctionSettings(
                enabled=True,
                max_inline_call_nesting=2,
            ),
            id="nesting-budget",
        ),
    ],
)
def test_inline_budget_blocks_findings(
    tmp_path: Path,
    source: str,
    settings: LowUseShortFunctionSettings,
) -> None:
    """A helper is not reported when inlining would exceed a configured budget."""
    findings = _run_rule(tmp_path, source, settings=settings)

    assert findings == ()


def test_usage_threshold_is_configurable(tmp_path: Path) -> None:
    """The maximum low-usage call-site count comes from rule settings."""
    source = """
        def clean(value):
            return value.strip()

        def first(value):
            return clean(value)

        def second(value):
            return clean(value)
    """

    strict_findings = _run_rule(
        tmp_path,
        source,
        settings=LowUseShortFunctionSettings(enabled=True, max_call_sites=1),
    )
    permissive_findings = _run_rule(
        tmp_path,
        source,
        settings=LowUseShortFunctionSettings(enabled=True, max_call_sites=2),
    )

    assert strict_findings == ()
    assert tuple(finding.subject_name for finding in permissive_findings) == ("clean",)


def test_required_api_surface_not_reported(tmp_path: Path) -> None:
    """Required API symbols are not reported even when short and low-use."""
    source = """
        def caller(resource):
            return resource.identity("x")

        class Resource:
            def __init__(self, value):
                self.value = value

            def identity(self, value):
                return value
    """

    findings = _run_rule(tmp_path, source)

    assert findings == ()


def _run_rule(
    tmp_path: Path,
    source: str,
    *,
    settings: LowUseShortFunctionSettings | None = None,
) -> tuple[RuleFinding, ...]:
    file_path = tmp_path / "sample.py"
    file_path.write_text(dedent(source).strip() + "\n", encoding="utf-8")
    parsed = PythonParser().parse(file_path, file_path.read_text(encoding="utf-8"))
    project = build_project((parsed.module,))
    rule_settings = settings or LowUseShortFunctionSettings(enabled=True)
    return run_rules(project, rules=(LowUseShortFunctionRule(rule_settings),))

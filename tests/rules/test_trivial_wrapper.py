from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from scb_check.rules.runner import run_rules
from scb_check.rules.trivial_wrapper import TrivialWrapperRule
from scb_check.tree_walking.languages.python import PythonParser
from scb_check.tree_walking.semantic import build_project


def test_trivial_wrapper_rule_flags_single_return_wrappers(tmp_path: Path) -> None:
    """The structural rule flags identity and project pass-through wrappers."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        def normalize(value):
            if value:
                return value.strip()
            return ""

        def identity(value):
            return value

        def clean(value):
            return normalize(value)
        """,
    ).strip() + "\n"
    project = build_project((PythonParser().parse(file_path, source).module,))

    findings = run_rules(project, rules=(TrivialWrapperRule(),))

    assert tuple(finding.subject_name for finding in findings) == (
        "identity",
        "clean",
    )
    assert {finding.rule_id for finding in findings} == {"trivial-wrapper"}


def test_trivial_wrapper_rule_uses_semantic_keep_reasons(tmp_path: Path) -> None:
    """Required API surfaces and meaningful effects are not reported."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        import json

        STATUS = "ready"

        def status():
            return STATUS

        def literal_status():
            return "ready"

        def parse_payload(value):
            return json.loads(value)

        class Resource:
            @property
            def identifier(self):
                return self._identifier

        class Encoder(BaseEncoder):
            def default(self, value):
                return value
        """,
    ).strip() + "\n"
    project = build_project((PythonParser().parse(file_path, source).module,))

    findings = run_rules(project, rules=(TrivialWrapperRule(),))

    assert findings == ()


def test_trivial_wrapper_rule_keeps_constant_value_providers(tmp_path: Path) -> None:
    """Constant value providers are not removable wrappers."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        STATUS_LABELS = {"ready": "Ready", "paused": "Paused"}

        def status_label_map():
            values = {"ready": "Ready", "paused": "Paused"}
            return values

        def literal_default_status_labels(
            values={"ready": "Ready", "paused": "Paused"},
        ):
            return values

        def named_default_status_labels(values=STATUS_LABELS):
            return values

        def identity(value):
            return value
        """,
    ).strip() + "\n"
    project = build_project((PythonParser().parse(file_path, source).module,))

    findings = run_rules(project, rules=(TrivialWrapperRule(),))

    assert tuple(finding.subject_name for finding in findings) == ("identity",)


def test_trivial_wrapper_rule_does_not_report_aliases(tmp_path: Path) -> None:
    """The cutover rule reports function symbols, not alias assignments."""
    file_path = tmp_path / "sample.py"
    source = dedent(
        """
        def real(value):
            if value:
                return value
            return None

        legacy = real
        """,
    ).strip() + "\n"
    project = build_project((PythonParser().parse(file_path, source).module,))

    findings = run_rules(project, rules=(TrivialWrapperRule(),))

    assert findings == ()

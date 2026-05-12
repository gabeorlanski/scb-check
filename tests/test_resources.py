from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from scb_check.resources import find_rule_document
from scb_check.resources import load_rule_ids
from scb_check.resources import rule_texts
from scb_check.resources import rules_file

if TYPE_CHECKING:
    import pytest


def _write_rule_file(path: Path, rule_id: str) -> None:
    path.write_text(
        f"""---
id: {rule_id}
language: python
severity: warning
message: env extra rule
rule:
  pattern: pass
""",
        encoding="utf-8",
    )


def _bundled_rule_documents() -> tuple[dict[str, object], ...]:
    return tuple(
        cast("dict[str, object]", document)
        for _, text in rule_texts()
        for document in yaml.safe_load_all(io.StringIO(text))
        if isinstance(document, dict)
    )


def test_extra_rules_named(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Extra rule files from the environment are returned by name."""
    extra_rules = tmp_path / "extra_rules.yaml"
    _write_rule_file(extra_rules, "env-extra-rule")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(extra_rules))

    named_texts = dict(rule_texts())

    assert extra_rules.name in named_texts
    assert "id: env-extra-rule" in named_texts[extra_rules.name]


def test_find_rule_document_returns_bundled_rule() -> None:
    """Bundled rule documents are findable by ID."""
    document = find_rule_document("chained-dict-get")

    assert document is not None
    assert document["id"] == "chained-dict-get"


def test_load_rule_ids_reads_combined_yaml(tmp_path: Path) -> None:
    """Rule IDs are loaded from a YAML rules file through resources."""
    rules_path = tmp_path / "rules.yaml"
    _write_rule_file(rules_path, "loaded-rule-id")

    assert load_rule_ids(rules_path) == frozenset({"loaded-rule-id"})


def test_extra_rules_combined(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Extra rule files from the environment are merged into the rules file."""
    extra_rules = tmp_path / "combined_extra_rules.yaml"
    _write_rule_file(extra_rules, "env-combined-extra-rule")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(extra_rules))

    with rules_file() as rules_path:
        combined_text = rules_path.read_text(encoding="utf-8")

    assert "id: env-combined-extra-rule" in combined_text


def test_bundled_rules_prioritized() -> None:
    """Bundled slop rules use severity and weight to mark priority."""
    documents = _bundled_rule_documents()

    warnings = tuple(
        document
        for document in documents
        if document.get("severity") == "warning"
    )
    infos = tuple(
        document for document in documents if document.get("severity") == "info"
    )

    assert warnings
    assert len(warnings) < len(infos)
    assert {document.get("severity") for document in documents} == {
        "info",
        "warning",
    }
    assert all(_metadata_weight(document) >= 5 for document in warnings)
    assert all(_metadata_weight(document) <= 1 for document in infos)


def test_fix_rules_warning_smells_info() -> None:
    """Obvious fixes are warnings while design smells remain informational."""
    documents_by_id = {
        cast("str", document["id"]): document
        for document in _bundled_rule_documents()
    }

    obvious_fix_rule_ids = {
        "duplicated-if-condition",
        "dict-get-default-none",
        "except-return-static-sentinel",
        "json-loads-read",
        "redundant-guard-same-return",
    }
    design_smell_rule_ids = {
        "defensive-function-isinstance-heavy",
        "init-populate-iterate-list",
        "nested-guard-invert",
        "repeated-validation-calls",
        "type-probe-ladder",
    }

    assert all(
        documents_by_id[rule_id]["severity"] == "warning"
        for rule_id in obvious_fix_rule_ids
    )
    assert all(
        _metadata_weight(documents_by_id[rule_id]) >= 5
        for rule_id in obvious_fix_rule_ids
    )
    assert all(
        documents_by_id[rule_id]["severity"] == "info"
        for rule_id in design_smell_rule_ids
    )


def _metadata_weight(document: dict[str, object]) -> int:
    metadata = document.get("metadata")
    assert isinstance(metadata, dict)
    typed_metadata = cast("dict[str, object]", metadata)
    weight = typed_metadata.get("weight")
    assert isinstance(weight, int)
    return weight

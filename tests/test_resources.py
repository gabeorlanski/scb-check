from __future__ import annotations

from pathlib import Path

from scb_check.resources import combined_slop_rules_file
from scb_check.resources import iter_slop_rule_texts


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


def test_iter_slop_rule_texts_includes_env_extra_file(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    extra_rules = tmp_path / "extra_rules.yaml"
    _write_rule_file(extra_rules, "env-extra-rule")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(extra_rules))

    named_texts = dict(iter_slop_rule_texts())

    assert extra_rules.name in named_texts
    assert "id: env-extra-rule" in named_texts[extra_rules.name]


def test_combined_slop_rules_file_includes_env_extra_file(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    extra_rules = tmp_path / "combined_extra_rules.yaml"
    _write_rule_file(extra_rules, "env-combined-extra-rule")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(extra_rules))

    with combined_slop_rules_file() as rules_path:
        combined_text = rules_path.read_text(encoding="utf-8")

    assert "id: env-combined-extra-rule" in combined_text

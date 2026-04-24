from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import FIXTURES

from scb_check.analysis.astgrep import run_sg


def test_missing_sg_returns_no_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing sg binary produces no ast-grep hits."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which", lambda _: None,
    )

    hits = run_sg((FIXTURES / "corpus" / "module_c.py",), rules_file)

    assert hits == ()


def test_sg_finds_bundled_rule() -> None:
    """Installed sg reports hits from bundled rules."""
    if shutil.which("sg") is None:
        pytest.skip("sg binary not available")

    project_root = Path(__file__).resolve().parents[2]
    rules_file = (
        project_root
        / "src"
        / "scb_check"
        / "resources"
        / "slop_rules"
        / "dict_patterns.yaml"
    )
    hits = run_sg((FIXTURES / "corpus" / "module_c.py",), rules_file)

    assert any(hit.rule_id == "chained-dict-get" for hit in hits)


def test_sg_skips_bad_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Malformed ast-grep JSON records are ignored."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")

    valid = (
        '{"file":"sample.py","range":{"start":{"line":0,"column":0},'
        '"end":{"line":0,"column":1}},"ruleId":"x","text":"x","message":"m"}'
    )
    missing_text = (
        '{"file":"sample.py","range":{"start":{"line":1,"column":0},'
        '"end":{"line":1,"column":1}},"ruleId":"y","message":"m"}'
    )

    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which", lambda _: "sg",
    )

    def fake_run(
        *_args: object, **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["sg"],
            returncode=0,
            stdout=f"{valid}\n{missing_text}\n",
            stderr="",
        )

    monkeypatch.setattr("scb_check.analysis.astgrep.subprocess.run", fake_run)

    hits = run_sg((tmp_path / "sample.py",), rules_file)

    assert len(hits) == 1
    assert hits[0].rule_id == "x"

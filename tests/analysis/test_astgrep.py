from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FIXTURES

from scb_check.analysis.astgrep import run_sg


def test_missing_ast_grep_returns_no_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing global and package-managed binaries produce no ast-grep hits."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(env_bin / "python"))
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which", lambda _: None,
    )

    hits = run_sg((FIXTURES / "corpus" / "module_c.py",), rules_file)

    assert hits == ()


def test_run_sg_prefers_global_sg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A global `sg` executable is used before package-managed fallbacks."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    ast_grep = env_bin / "ast-grep"
    ast_grep.write_text("", encoding="utf-8")
    ast_grep.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(env_bin / "python"))
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which",
        lambda binary: "/global/sg" if binary == "sg" else None,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("scb_check.analysis.astgrep.subprocess.run", fake_run)

    hits = run_sg((tmp_path / "sample.py",), rules_file)

    assert hits == ()
    assert commands[0][0] == "/global/sg"


def test_run_sg_falls_back_to_python_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Package-managed `ast-grep` is used when global `sg` is missing."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    ast_grep = env_bin / "ast-grep"
    ast_grep.write_text("", encoding="utf-8")
    ast_grep.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(env_bin / "python"))
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which",
        lambda _: None,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("scb_check.analysis.astgrep.subprocess.run", fake_run)

    hits = run_sg((tmp_path / "sample.py",), rules_file)

    assert hits == ()
    assert commands[0][0] == str(ast_grep)


def test_run_sg_falls_back_after_exec_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A global `sg` execution failure retries package-managed ast-grep."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    ast_grep = env_bin / "ast-grep"
    ast_grep.write_text("", encoding="utf-8")
    ast_grep.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(env_bin / "python"))
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which",
        lambda binary: "/global/sg" if binary == "sg" else None,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == "/global/sg":
            raise OSError("exec format error")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("scb_check.analysis.astgrep.subprocess.run", fake_run)

    hits = run_sg((tmp_path / "sample.py",), rules_file)

    assert hits == ()
    assert [command[0] for command in commands] == ["/global/sg", str(ast_grep)]


def test_run_sg_falls_back_after_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A global `sg` non-zero exit retries package-managed ast-grep."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    ast_grep = env_bin / "ast-grep"
    ast_grep.write_text("", encoding="utf-8")
    ast_grep.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(env_bin / "python"))
    monkeypatch.setattr(
        "scb_check.analysis.astgrep.shutil.which",
        lambda binary: "/global/sg" if binary == "sg" else None,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=1 if command[0] == "/global/sg" else 0,
            stdout="",
            stderr="bad global sg",
        )

    monkeypatch.setattr("scb_check.analysis.astgrep.subprocess.run", fake_run)

    hits = run_sg((tmp_path / "sample.py",), rules_file)

    assert hits == ()
    assert [command[0] for command in commands] == ["/global/sg", str(ast_grep)]


def test_sg_finds_bundled_rule() -> None:
    """An available ast-grep executable reports hits from bundled rules."""
    env_bin = Path(sys.executable).parent
    if shutil.which("sg") is None and not (env_bin / "ast-grep").is_file():
        pytest.skip("ast-grep binary not available")

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

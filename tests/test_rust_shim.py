from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scb_check import cli


def test_rust_command_prefers_packaged_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Installed wheels use the packaged Rust binary before source fallbacks."""
    packaged = tmp_path / "package" / "bin" / "scb-check"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("", encoding="utf-8")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")

    monkeypatch.delenv("SCB_CHECK_RUST_BIN", raising=False)

    assert cli._rust_command(packaged, repo_root, ["--version"]) == [  # noqa: SLF001
        str(packaged),
        "--version",
    ]


def test_rust_command_override_wins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The explicit binary override remains highest priority."""
    packaged = tmp_path / "package" / "bin" / "scb-check"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("", encoding="utf-8")
    override = tmp_path / "override-scb-check"
    monkeypatch.setenv("SCB_CHECK_RUST_BIN", str(override))

    assert cli._rust_command(packaged, tmp_path, ["check", "."]) == [  # noqa: SLF001
        str(override),
        "check",
        ".",
    ]


def test_main_exits_with_packaged_binary_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The public Python entrypoint propagates the Rust process exit code."""
    packaged = tmp_path / "package" / "bin" / "scb-check"
    packaged.parent.mkdir(parents=True)
    packaged.write_text("", encoding="utf-8")
    calls: list[tuple[list[str], Path, bool]] = []

    monkeypatch.setattr(cli, "_package_binary", lambda: packaged)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "argv", ["scb-check", "check", "."])

    def fake_run(command: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 7

    assert calls == [([str(packaged), "check", "."], tmp_path, False)]

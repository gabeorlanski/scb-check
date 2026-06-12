"""Rust entrypoint shim for `scb-check` during the cutover."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the Rust `scb-check` binary."""
    package_binary = _package_binary()
    repo_root = _repo_root()
    command = _rust_command(package_binary, repo_root, sys.argv[1:])
    completed = subprocess.run(command, cwd=repo_root, check=False)  # noqa: S603
    raise SystemExit(completed.returncode)


def _package_binary() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return Path(__file__).resolve().parent / "bin" / f"scb-check{suffix}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rust_command(package_binary: Path, repo_root: Path, args: list[str]) -> list[str]:
    override = os.environ.get("SCB_CHECK_RUST_BIN")
    if override:
        return [override, *args]

    if package_binary.is_file():
        return [str(package_binary), *args]

    binary = repo_root / "target" / "debug" / "scb-check"
    if binary.is_file():
        return [str(binary), *args]

    if (repo_root / "Cargo.toml").is_file():
        return ["cargo", "run", "-q", "-p", "scb-check", "--", *args]

    message = (
        "scb-check Rust binary is not available; set `SCB_CHECK_RUST_BIN` "
        "to the packaged binary path"
    )
    sys.stderr.write(f"{message}\n")
    raise SystemExit(2)

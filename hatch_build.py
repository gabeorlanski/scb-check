"""Build hook that packages the Rust `scb-check` binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from packaging.tags import sys_tags


class CustomBuildHook(BuildHookInterface):
    """Build the Rust CLI and include it in wheels."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Build the Rust binary before wheel assembly."""
        _ = version
        if self.target_name != "wheel":
            return

        build_data["pure_python"] = False
        build_data["infer_tag"] = False
        build_data["tag"] = _binary_wheel_tag()

        root = Path(self.root)
        cargo = shutil.which("cargo")
        if cargo is None:
            msg = "cargo is required to build the scb-check wheel"
            raise RuntimeError(msg)

        binary = root / "target" / "release" / _binary_name()
        subprocess.run(  # noqa: S603
            [cargo, "build", "--release", "-p", "scb-check"],
            cwd=root,
            check=True,
        )

        shared_scripts = build_data.setdefault("shared_scripts", {})
        shared_scripts[str(binary)] = _binary_name()


def _binary_name() -> str:
    if os.name == "nt":
        return "scb-check.exe"
    return "scb-check"


def _binary_wheel_tag() -> str:
    """Return the build host's compatible, Python-ABI-independent wheel tag."""
    platform = next(sys_tags()).platform
    return f"py3-none-{platform}"

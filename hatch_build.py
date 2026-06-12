"""Build hook that packages the Rust `scb-check` binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Build the Rust CLI and include it in wheels."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Build the Rust binary before wheel assembly."""
        _ = version
        if self.target_name != "wheel":
            return

        build_data["pure_python"] = False
        build_data["infer_tag"] = True

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

        force_include = build_data.setdefault("force_include", {})
        force_include[str(binary)] = f"src/scb_check/bin/{_binary_name()}"


def _binary_name() -> str:
    if os.name == "nt":
        return "scb-check.exe"
    return "scb-check"

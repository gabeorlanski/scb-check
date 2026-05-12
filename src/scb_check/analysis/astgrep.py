"""Run ast-grep rules and convert matches to findings."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from scb_check.logging import get_logger
from scb_check.models import AstGrepHit
from scb_check.models import AstGrepSeverity

logger = get_logger(__name__)

_AST_GREP_BINARIES = ("ast-grep", "sg")


def run_sg(files: tuple[Path, ...], rules_path: Path) -> tuple[AstGrepHit, ...]:
    """Invoke the ``sg`` binary against ``files`` using ``rules_path``.

    Returns an empty tuple — never raises — when the binary is missing,
    the subprocess fails, the exit code is non-zero, or the JSON payload
    is unparseable. A missing ``sg`` is treated as a degraded run, not a
    hard failure, so scb-check still produces clone and erosion numbers.
    Line and column numbers in the returned hits are 1-indexed.
    """
    command = _command(files, rules_path)
    if command is None:
        return ()

    result = _run_command(command)
    if result is None:
        return ()

    return _parse_hits(result.stdout)


def _command(files: tuple[Path, ...], rules_path: Path) -> list[str] | None:
    if not files or not rules_path.exists():
        logger.warning(
            "no files to scan or rules file missing",
            files=files,
            rules_path=rules_path,
            rules_exists=rules_path.exists(),
        )
        return None

    ast_grep_binary = _ast_grep_binary()
    if ast_grep_binary is None:
        logger.warning("ast-grep binary not found", binary="ast-grep")
        return None

    return [
        ast_grep_binary,
        "scan",
        "--json=stream",
        "-r",
        str(rules_path),
        *[str(path) for path in files],
    ]


def _ast_grep_binary() -> str | None:
    for binary in _AST_GREP_BINARIES:
        if (candidate := _python_env_executable(binary)) is not None:
            return str(candidate)

    for binary in _AST_GREP_BINARIES:
        if (candidate := shutil.which(binary)) is not None:
            return candidate

    return None


def _python_env_executable(binary: str) -> Path | None:
    candidate = Path(sys.executable).parent / binary
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate

    return None


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("failed to execute ast-grep", error=str(exc))
        return None

    if result.returncode == 0:
        return result

    logger.warning(
        "ast-grep returned non-zero",
        returncode=result.returncode,
        stderr=result.stderr.strip(),
    )
    return None  # scbc ignore[redundant-return-none]


def _parse_hits(stdout: str) -> tuple[AstGrepHit, ...]:
    hits = tuple(
        hit
        for line in stdout.splitlines()
        if line.strip()
        if (hit := _parse_hit(line)) is not None
    )
    return tuple(
        sorted(
            hits,
            key=lambda hit: (
                hit.file.as_posix(),
                hit.line,
                hit.col,
                hit.rule_id,
            ),
        ),
    )


def _parse_hit(line: str) -> AstGrepHit | None:
    try:
        payload = json.loads(line)
        start = payload["range"]["start"]
        end = payload["range"]["end"]
        return AstGrepHit(
            file=Path(payload["file"]).resolve(),
            line=int(start["line"]) + 1,
            end_line=int(end["line"]) + 1,
            col=int(start["column"]),
            end_col=int(end["column"]),
            rule_id=str(payload["ruleId"]),
            matched_text=str(payload["text"]),
            message=str(payload["message"]),
            severity=_severity(payload.get("severity")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("failed to parse ast-grep output", error=str(exc))
        return None


def _severity(value: object) -> AstGrepSeverity:
    return (
        cast("AstGrepSeverity", value)
        if value in {"info", "warning", "critical"}
        else "warning"
    )

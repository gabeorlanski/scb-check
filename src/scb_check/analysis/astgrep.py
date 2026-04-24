"""Run ast-grep rules and convert matches to findings."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from scb_check.logging import get_logger
from scb_check.models import AstGrepHit

logger = get_logger(__name__)


def run_sg(files: tuple[Path, ...], rules_path: Path) -> tuple[AstGrepHit, ...]:
    """Invoke the ``sg`` binary against ``files`` using ``rules_path``.

    Returns an empty tuple — never raises — when the binary is missing,
    the subprocess fails, the exit code is non-zero, or the JSON payload
    is unparseable. A missing ``sg`` is treated as a degraded run, not a
    hard failure, so scb-check still produces clone and erosion numbers.
    Line and column numbers in the returned hits are 1-indexed.
    """
    if not files or not rules_path.exists():
        logger.warning(
            "no files to scan or rules file missing",
            files=files,
            rules_path=rules_path,
            rules_exists=rules_path.exists(),
        )
        return ()

    sg_binary = shutil.which("sg")
    if sg_binary is None:
        logger.warning("ast-grep binary not found", binary="sg")
        return ()

    command = [
        sg_binary,
        "scan",
        "--json=stream",
        "-r",
        str(rules_path),
        *[str(path) for path in files],
    ]
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("failed to execute ast-grep", error=str(exc))
        return ()

    if result.returncode != 0:
        logger.warning(
            "ast-grep returned non-zero",
            returncode=result.returncode,
            stderr=result.stderr.strip(),
        )
        return ()

    hits: list[AstGrepHit] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        try:
            payload = json.loads(line)
            start = payload["range"]["start"]
            end = payload["range"]["end"]
            file_path = Path(payload["file"]).resolve()
            hits.append(
                AstGrepHit(
                    file=file_path,
                    line=int(start["line"]) + 1,
                    end_line=int(end["line"]) + 1,
                    col=int(start["column"]),
                    end_col=int(end["column"]),
                    rule_id=str(payload["ruleId"]),
                    matched_text=str(payload["text"]),
                    message=str(payload["message"]),
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("failed to parse ast-grep output", error=str(exc))

    hits.sort(
        key=lambda hit: (
            hit.file.as_posix(),
            hit.line,
            hit.col,
            hit.rule_id,
        ),
    )
    return tuple(hits)

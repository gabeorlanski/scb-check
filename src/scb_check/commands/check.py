"""Register and implement the `scb-check check` command."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from scb_check.config import ConfigError
from scb_check.config import load_config
from scb_check.logging import configure_logging
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze
from scb_check.reporting.render import render_flags
from scb_check.reporting.score import compute_report


def register_check(app: typer.Typer) -> None:
    """Register the `check` subcommand on `app`."""

    @app.command("check")
    def check(
        path: Annotated[Path, typer.Argument()],
        *,
        report: Annotated[
            bool | None,
            typer.Option("--report", help="Emit JSON report."),
        ] = None,
        config_path: Annotated[
            Path | None,
            typer.Option("--config", help="Explicit config path."),
        ] = None,
        verbosity: Annotated[
            int,
            typer.Option(
                "-v",
                "--verbosity",
                count=True,
                help="Increase logging detail. -v enables info logs, -vv enables debug logs.",
            ),
        ] = 0,
        include_all: Annotated[
            bool,
            typer.Option(
                "--include-all",
                help="Include all ast-grep findings, including ignored and boundary-suppressed findings.",
            ),
        ] = False,
    ) -> None:
        configure_logging(verbosity)

        try:
            config = load_config(config_path, Path.cwd())
            result = analyze(path, config, include_all=include_all)
        except (ConfigError, IgnoreDirectiveError, OSError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

        if not result.flags.total_loc_by_file:
            typer.echo(f"no Python files could be parsed at {path}", err=True)
            raise typer.Exit(code=2)

        if report:
            report_payload = compute_report(result.flags)
            json.dump(asdict(report_payload), sys.stdout)
            return

        output = render_flags(
            result.flags,
            result.source_lines_by_file,
            context_lines=config.context_lines,
        )
        if output:
            typer.echo(output)

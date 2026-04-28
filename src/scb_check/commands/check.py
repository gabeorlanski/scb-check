"""Implement the `scb-check check` command."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal, TypedDict, Unpack

import click
import typer
from typer.core import TyperCommand

from scb_check.config import ConfigError
from scb_check.config import load_config
from scb_check.logging import configure_logging
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze
from scb_check.reporting.render import render_flags
from scb_check.reporting.score import compute_report

_ContextSetting = str | int | bool | tuple[str, ...] | list[str] | None
_OutputMode = Literal["report", "duplicates"]
_FlagValue = Literal[False, True]
_OUTPUT_MODE_KEY = "scb_check_output_mode"
_OUTPUT_MODES: dict[str, _OutputMode] = {
    "report": "report",
    "duplicates": "duplicates",
}


class _TyperCommandKwargs(TypedDict, total=False):
    context_settings: dict[str, _ContextSetting] | None
    callback: Callable[..., None] | None
    params: list[click.Parameter] | None
    help: str | None
    epilog: str | None
    short_help: str | None
    options_metavar: str | None
    add_help_option: bool
    no_args_is_help: bool
    hidden: bool
    deprecated: bool
    rich_markup_mode: Literal["markdown", "rich"] | None
    rich_help_panel: str | None


class _CheckCommand(TyperCommand):
    def __init__(
        self,
        name: str | None,
        **kwargs: Unpack[_TyperCommandKwargs],
    ) -> None:
        params = kwargs.get("params")
        kwargs["params"] = [*_output_mode_options(), *(params or [])]
        super().__init__(name, **kwargs)


def _output_mode_options() -> list[click.Option]:
    return [
        click.Option(
            ["--report"],
            is_flag=True,
            expose_value=False,
            callback=_store_output_mode("report"),
            help="Emit JSON report.",
        ),
        click.Option(
            ["--duplicates-only"],
            is_flag=True,
            expose_value=False,
            callback=_store_output_mode("duplicates"),
            help="Only emit duplicate-structure findings.",
        ),
    ]


def _store_output_mode(
    mode: _OutputMode,
) -> Callable[[click.Context, click.Parameter, _FlagValue], None]:
    def callback(
        ctx: click.Context,
        _param: click.Parameter,
        value: _FlagValue,
    ) -> None:
        if not value:
            return

        existing = ctx.meta.get(_OUTPUT_MODE_KEY)
        if existing is not None and existing != mode:
            raise click.BadParameter(
                "`--report` and `--duplicates-only` cannot be used together",
            )
        ctx.meta[_OUTPUT_MODE_KEY] = mode

    return callback


def _output_mode(ctx: typer.Context) -> _OutputMode | None:
    value = ctx.meta.get(_OUTPUT_MODE_KEY)
    return _OUTPUT_MODES.get(value) if isinstance(value, str) else None


CHECK_COMMAND_CLASS = _CheckCommand


def check(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument()],
    *,
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
    """Run analysis for `path` and emit the selected output format."""
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

    output_mode = _output_mode(ctx)
    if output_mode == "report":
        report_payload = compute_report(result.flags)
        json.dump(asdict(report_payload), sys.stdout)
        return

    flags = result.flags
    if output_mode == "duplicates":
        flags = replace(
            result.flags,
            ast_grep_hits=(),
            high_cc_functions=(),
            high_cog_functions=(),
        )
    output = render_flags(
        flags,
        result.source_lines_by_file,
        context_lines=config.context_lines,
    )
    if output:
        typer.echo(output)

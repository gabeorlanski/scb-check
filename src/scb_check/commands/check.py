"""Implement the `scb-check check` command."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import asdict
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
_OutputFormat = Literal["human", "json"]
_FlagValue = Literal[False, True]
_OUTPUT_FORMAT_KEY = "scb_check_output_format"
_REPORT_KEY = "scb_check_report"
_DISABLE_SG_KEY = "scb_check_disable_sg"
_MIN_DUPLICATE_LINES_KEY = "scb_check_min_duplicate_lines"
_OUTPUT_FORMATS: dict[str, _OutputFormat] = {
    "human": "human",
    "json": "json",
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
        command_options = [
            click.Option(
                ["--output-format"],
                type=click.Choice(tuple(_OUTPUT_FORMATS)),
                default="human",
                show_default=True,
                expose_value=False,
                callback=_store_output_format,
                help="Choose output format (default: human).",
            ),
            click.Option(
                ["--report"],
                is_flag=True,
                expose_value=False,
                callback=_store_flag(_REPORT_KEY),
                help="Emit JSON report.",
            ),
            click.Option(
                ["--disable-sg"],
                is_flag=True,
                expose_value=False,
                callback=_store_flag(_DISABLE_SG_KEY),
                help="Disable ast-grep subprocess analysis.",
            ),
            click.Option(
                ["--min-duplicate-lines"],
                type=click.IntRange(min=1),
                expose_value=False,
                callback=_store_min_duplicate_lines,
                help="Only emit duplicate groups with at least N duplicated SLOC lines.",
            ),
        ]
        kwargs["params"] = [*command_options, *(params or [])]
        super().__init__(name, **kwargs)


def _store_output_format(
    ctx: click.Context,
    param: click.Parameter,
    value: str,
) -> None:
    if param.name is None:
        return
    if ctx.get_parameter_source(param.name) is not click.core.ParameterSource.COMMANDLINE:
        return
    if value in _OUTPUT_FORMATS:
        ctx.meta[_OUTPUT_FORMAT_KEY] = value


def _store_min_duplicate_lines(
    ctx: click.Context,
    _param: click.Parameter,
    value: int | None,
) -> None:
    if value is not None:
        ctx.meta[_MIN_DUPLICATE_LINES_KEY] = value


def _store_flag(
    key: str,
) -> Callable[[click.Context, click.Parameter, _FlagValue], None]:
    def callback(
        ctx: click.Context,
        _param: click.Parameter,
        value: _FlagValue,
    ) -> None:
        if value:
            ctx.meta[key] = True

    return callback


def _resolve_output(ctx: typer.Context) -> _OutputFormat:
    explicit_format = _explicit_output_format(ctx)
    report = bool(ctx.meta.get(_REPORT_KEY, False))

    if report and explicit_format == "human":
        raise ValueError("`--report` and `--output-format human` cannot be used together")

    return "json" if report else explicit_format or "human"


def _explicit_output_format(ctx: typer.Context) -> _OutputFormat | None:
    value = ctx.meta.get(_OUTPUT_FORMAT_KEY)
    return _OUTPUT_FORMATS.get(value) if isinstance(value, str) else None


def _min_duplicate_lines(ctx: typer.Context) -> int | None:
    value = ctx.meta.get(_MIN_DUPLICATE_LINES_KEY)
    return value if isinstance(value, int) else None


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
    try:
        output_format = _resolve_output(ctx)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    configure_logging(verbosity)

    try:
        config = load_config(config_path, Path.cwd())
        result = analyze(
            path,
            config,
            include_all=include_all,
            disable_sg=bool(ctx.meta.get(_DISABLE_SG_KEY, False)),
        )
    except (ConfigError, IgnoreDirectiveError, OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    if not result.flags.total_loc_by_file:
        typer.echo(f"no Python files could be parsed at {path}", err=True)
        raise typer.Exit(code=2)

    if output_format == "json":
        report_payload = compute_report(result.flags)
        json.dump(asdict(report_payload), sys.stdout)
        return

    flags = result.flags
    min_duplicate_lines = _min_duplicate_lines(ctx)
    if min_duplicate_lines is None:
        output = render_flags(
            flags,
            result.source_lines_by_file,
            context_lines=config.context_lines,
        )
    else:
        output = render_flags(
            flags,
            result.source_lines_by_file,
            context_lines=config.context_lines,
            min_duplicate_lines=min_duplicate_lines,
        )
    if output:
        typer.echo(output)

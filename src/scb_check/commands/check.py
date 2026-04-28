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
_OutputFormat = Literal["human", "json"]
_FlagValue = Literal[False, True]
_OUTPUT_FORMAT_KEY = "scb_check_output_format"
_REPORT_KEY = "scb_check_report"
_DUPLICATES_ONLY_KEY = "scb_check_duplicates_only"
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
        kwargs["params"] = [*_check_options(), *(params or [])]
        super().__init__(name, **kwargs)


def _check_options() -> list[click.Option]:
    return [
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
            ["--duplicates-only"],
            is_flag=True,
            expose_value=False,
            callback=_store_flag(_DUPLICATES_ONLY_KEY),
            help="Only emit duplicate-structure findings.",
        ),
    ]


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


def _resolve_output(ctx: typer.Context) -> tuple[_OutputFormat, bool]:
    explicit_format = _explicit_output_format(ctx)
    report = bool(ctx.meta.get(_REPORT_KEY, False))
    duplicates_only = bool(ctx.meta.get(_DUPLICATES_ONLY_KEY, False))

    if report and duplicates_only:
        raise ValueError("`--report` and `--duplicates-only` cannot be used together")
    if report and explicit_format == "human":
        raise ValueError("`--report` and `--output-format human` cannot be used together")

    output_format: _OutputFormat = "json" if report else explicit_format or "human"
    if output_format == "json" and duplicates_only:
        raise ValueError(
            "`--output-format json` and `--duplicates-only` cannot be used together",
        )
    return output_format, duplicates_only


def _explicit_output_format(ctx: typer.Context) -> _OutputFormat | None:
    value = ctx.meta.get(_OUTPUT_FORMAT_KEY)
    return _OUTPUT_FORMATS.get(value) if isinstance(value, str) else None


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
        output_format, duplicates_only = _resolve_output(ctx)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

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

    if output_format == "json":
        report_payload = compute_report(result.flags)
        json.dump(asdict(report_payload), sys.stdout)
        return

    flags = result.flags
    if duplicates_only:
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

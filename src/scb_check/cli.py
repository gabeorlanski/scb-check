"""Top-level Typer application wiring for `scb-check`."""

from __future__ import annotations

from importlib import metadata
from typing import Annotated

import typer

from scb_check.commands.check import register_check
from scb_check.commands.rule import register_rule

main = typer.Typer(add_completion=False)


@main.callback(invoke_without_command=True)
def callback(
    *,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """scb-check CLI."""
    if not version:
        return

    typer.echo(metadata.version("scb-check"))
    raise typer.Exit


register_check(main)
register_rule(main)

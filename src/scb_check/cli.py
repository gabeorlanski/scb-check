"""Top-level Typer application wiring for `scb-check`."""

from __future__ import annotations

from importlib import metadata
from typing import Annotated

import typer

from scb_check.commands.check import CHECK_COMMAND_CLASS
from scb_check.commands.check import check
from scb_check.commands.rule import rule

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


main.command("check", cls=CHECK_COMMAND_CLASS)(check)
main.command("rule")(rule)

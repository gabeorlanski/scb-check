"""Register and implement the `scb-check rule` command."""

from __future__ import annotations

import io
from typing import Annotated, cast

import typer
import yaml

from scb_check.resources import rule_texts


def register_rule(app: typer.Typer) -> None:
    """Register the `rule` subcommand on `app`."""

    @app.command("rule")
    def rule(
        rule_name: Annotated[str, typer.Argument(help="ast-grep rule id")],
    ) -> None:
        try:
            rule_payload = _find_rule(rule_name)
        except (OSError, yaml.YAMLError) as exc:
            typer.echo(f"failed to load rules: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if rule_payload is None:
            typer.echo(f"rule not found: {rule_name}", err=True)
            raise typer.Exit(code=2)

        rendered = yaml.safe_dump(rule_payload, sort_keys=False).rstrip()
        typer.echo(rendered)


def _find_rule(rule_name: str) -> dict[str, str] | None:
    matches = (
        cast("dict[str, str]", document)
        for _, text in rule_texts()
        for document in yaml.safe_load_all(io.StringIO(text))
        if isinstance(document, dict) and document.get("id") == rule_name
    )
    return next(matches, None)

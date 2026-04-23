from __future__ import annotations

import io
from typing import Annotated, Any

import typer
import yaml

from scb_check.resources import iter_slop_rule_texts


def register_rule(app: typer.Typer) -> None:
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


def _find_rule(rule_name: str) -> dict[str, Any] | None:
    for _, text in iter_slop_rule_texts():
        for document in yaml.safe_load_all(io.StringIO(text)):
            if not isinstance(document, dict):
                continue
            if document.get("id") == rule_name:
                return document
    return None

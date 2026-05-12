"""Implement the `scb-check rule` command."""

from __future__ import annotations

from typing import Annotated

import typer
import yaml

from scb_check.resources import RuleDocument
from scb_check.resources import find_rule_document
from scb_check.rules.registry import structural_rule_metadata


def rule(
    rule_name: Annotated[str, typer.Argument(help="rule id")],
) -> None:
    """Print bundled ast-grep YAML or structural rule metadata."""
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


def _find_rule(rule_name: str) -> RuleDocument | None:
    ast_grep_rule = find_rule_document(rule_name)
    if ast_grep_rule is not None:
        return ast_grep_rule

    metadata = structural_rule_metadata(rule_name)
    return dict(metadata) if metadata is not None else None

"""Structural rule runner."""

from __future__ import annotations

from scb_check.rules.registry import Rule
from scb_check.rules.registry import structural_rules
from scb_check.tree_walking.models import ProjectIR
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import RuleTarget
from scb_check.tree_walking.semantic import RuleContext


def run_rules(
    project: ProjectIR,
    rules: tuple[Rule, ...] | None = None,
) -> tuple[RuleFinding, ...]:
    """Run structural `rules` over supported project subjects."""
    # None means use the registry; an empty tuple intentionally disables rules.
    active_rules = rules if rules is not None else structural_rules()
    context = RuleContext(project)
    findings: list[RuleFinding] = []
    for module in project.modules:
        for symbol in module.symbols:
            findings.extend(
                finding
                for rule in active_rules
                if rule.target is RuleTarget.SYMBOL
                and symbol.language in rule.languages
                for finding in [rule.check(symbol, context)]
                if finding is not None
            )
    return tuple(findings)

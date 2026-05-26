"""Static structural rule registry."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import ClassVar, Protocol

from scb_check.rules.low_use_short_function import LowUseShortFunctionRule
from scb_check.rules.settings import LowUseShortFunctionSettings
from scb_check.rules.trivial_wrapper import TrivialWrapperRule
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import RuleTarget
from scb_check.tree_walking.models import Severity
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.semantic import RuleContext


class Rule(Protocol):
    """Protocol implemented by structural rules."""

    id: ClassVar[str]
    severity: ClassVar[Severity]
    languages: ClassVar[frozenset[Language]]
    target: ClassVar[RuleTarget]
    description: ClassVar[str]

    def check(self, symbol: SymbolIR, context: RuleContext) -> RuleFinding | None:
        """Return a finding when `symbol` violates this rule."""


@dataclass(slots=True)
class RuleRegistry:
    """Mutable registry for structural rule instances."""

    rules: dict[str, Rule] = field(default_factory=dict)

    def register(self, rule: Rule) -> None:
        """Register `rule`, failing on duplicate IDs."""
        if rule.id in self.rules:
            raise ValueError(f"duplicate structural rule id: {rule.id}")
        self.rules[rule.id] = rule

    def get(self, rule_id: str) -> Rule | None:
        """Return the rule registered for `rule_id`, if present."""
        return self.rules.get(rule_id)

    def all(self) -> tuple[Rule, ...]:
        """Return registered rules in insertion order."""
        return tuple(self.rules.values())

    def ids(self) -> frozenset[str]:
        """Return all registered rule IDs."""
        return frozenset(self.rules)


RULE_REGISTRY = RuleRegistry()
RULE_REGISTRY.register(TrivialWrapperRule())
RULE_REGISTRY.register(LowUseShortFunctionRule())


type RuleMetadataValue = str | list[str]


def structural_rules() -> tuple[Rule, ...]:
    """Return all registered structural rules."""
    return RULE_REGISTRY.all()


def configured_structural_rules(
    low_use_short_function: LowUseShortFunctionSettings,
) -> tuple[Rule, ...]:
    """Return structural rules using runtime configuration."""
    return (TrivialWrapperRule(), LowUseShortFunctionRule(low_use_short_function))


def structural_rule_ids() -> frozenset[str]:
    """Return all structural rule IDs."""
    return RULE_REGISTRY.ids()


def structural_rule_metadata(rule_id: str) -> dict[str, RuleMetadataValue] | None:
    """Return YAML-serializable metadata for a structural rule."""
    rule = RULE_REGISTRY.get(rule_id)
    return (
        {
            "id": rule.id,
            "language": [language.value for language in sorted(rule.languages)],
            "severity": rule.severity.value,
            "target": rule.target.value,
            "message": rule.description,
        }
        if rule is not None
        else None
    )

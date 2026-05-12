from __future__ import annotations

import pytest

from scb_check.rules.registry import RuleRegistry
from scb_check.rules.trivial_wrapper import TrivialWrapperRule


def test_rule_registry_registers_and_gets_rules() -> None:
    """RuleRegistry stores rules by ID."""
    registry = RuleRegistry()
    rule = TrivialWrapperRule()

    registry.register(rule)

    assert registry.get("trivial-wrapper") is rule
    assert registry.ids() == frozenset({"trivial-wrapper"})
    assert registry.all() == (rule,)


def test_rule_registry_rejects_duplicate_ids() -> None:
    """RuleRegistry fails fast when IDs collide."""
    registry = RuleRegistry()
    registry.register(TrivialWrapperRule())

    with pytest.raises(ValueError, match="duplicate structural rule id"):
        registry.register(TrivialWrapperRule())

"""Structural rule for removable pass-through wrappers."""

from __future__ import annotations

from typing import ClassVar

from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import RuleTarget
from scb_check.tree_walking.models import Severity
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.semantic import RuleContext


class TrivialWrapperRule:
    """Flag single-return wrappers with no semantic reason to exist."""

    id: ClassVar[str] = "trivial-wrapper"
    severity: ClassVar[Severity] = Severity.WARNING
    languages: ClassVar[frozenset[Language]] = frozenset({Language.PYTHON})
    target: ClassVar[RuleTarget] = RuleTarget.SYMBOL
    description: ClassVar[str] = "Single-return wrapper adds no behavior"

    def check(self, symbol: SymbolIR, context: RuleContext) -> RuleFinding | None:
        """Return a finding when `symbol` is a removable wrapper."""
        if not _is_trivial_candidate(symbol, context):
            return None
        return RuleFinding(
            rule_id=self.id,
            severity=self.severity,
            message=f"`{symbol.name}` adds no behavior",
            span=symbol.span,
            subject_name=symbol.name,
            subject_qualified_name=symbol.qualified_name,
            subject_kind=symbol.kind,
        )


def _is_trivial_candidate(symbol: SymbolIR, context: RuleContext) -> bool:
    return (
        symbol.kind in {SymbolKind.FUNCTION, SymbolKind.METHOD}
        and not context.is_required_api_surface(symbol)
        and not context.return_has_meaningful_effects(symbol)
        and (
            context.returns_forwarded_parameter(symbol)
            or context.returned_project_call_forwards_parameters(symbol)
        )
    )

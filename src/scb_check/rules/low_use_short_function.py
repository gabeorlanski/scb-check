"""Structural rule for short helpers that are cheap to inline."""

from __future__ import annotations

from typing import ClassVar

from scb_check.rules.settings import LowUseShortFunctionSettings
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import ReferenceIR
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import RuleTarget
from scb_check.tree_walking.models import Severity
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.semantic import RuleContext

_FUNCTION_KINDS = frozenset({SymbolKind.FUNCTION, SymbolKind.METHOD})


class LowUseShortFunctionRule:
    """Flag short low-use functions when inlining stays within caller budgets."""

    id: ClassVar[str] = "low-use-short-function"
    severity: ClassVar[Severity] = Severity.INFO
    languages: ClassVar[frozenset[Language]] = frozenset({Language.PYTHON})
    target: ClassVar[RuleTarget] = RuleTarget.SYMBOL
    description: ClassVar[str] = "Short low-use function can be inlined safely"

    def __init__(
        self,
        settings: LowUseShortFunctionSettings | None = None,
    ) -> None:
        """Initialize the rule with inline-safety settings."""
        self.settings = settings or LowUseShortFunctionSettings()

    def check(self, symbol: SymbolIR, context: RuleContext) -> RuleFinding | None:
        """Return a finding when `symbol` is a safe low-use inline candidate."""
        if not self.settings.enabled:
            return None
        if not _is_candidate_shape(symbol, context, self.settings):
            return None
        call_sites = context.call_sites_for_symbol(symbol)
        if not _has_low_usage(call_sites, self.settings):
            return None
        if not _all_callers_stay_within_budgets(symbol, call_sites, self.settings):
            return None
        return RuleFinding(
            rule_id=self.id,
            severity=self.severity,
            message=_message(symbol, call_sites),
            span=symbol.span,
            subject_name=symbol.name,
            subject_qualified_name=symbol.qualified_name,
            subject_kind=symbol.kind,
        )


# Re-exported from this module so callers can configure the rule from one import.
__all__ = ["LowUseShortFunctionRule", "LowUseShortFunctionSettings"]


def _is_candidate_shape(
    symbol: SymbolIR,
    context: RuleContext,
    settings: LowUseShortFunctionSettings,
) -> bool:
    return (
        symbol.kind in _FUNCTION_KINDS
        and not context.is_required_api_surface(symbol)
        and symbol.sloc <= settings.max_function_sloc
    )


def _has_low_usage(
    call_sites: tuple[tuple[SymbolIR, ReferenceIR], ...],
    settings: LowUseShortFunctionSettings,
) -> bool:
    return 1 <= len(call_sites) <= settings.max_call_sites


def _all_callers_stay_within_budgets(
    symbol: SymbolIR,
    call_sites: tuple[tuple[SymbolIR, ReferenceIR], ...],
    settings: LowUseShortFunctionSettings,
) -> bool:
    return all(
        _caller_stays_within_budgets(symbol, caller, references, settings)
        for caller, references in _references_by_caller(call_sites)
    )


def _references_by_caller(
    call_sites: tuple[tuple[SymbolIR, ReferenceIR], ...],
) -> tuple[tuple[SymbolIR, tuple[ReferenceIR, ...]], ...]:
    callers: dict[str, SymbolIR] = {}
    references: dict[str, list[ReferenceIR]] = {}
    for caller, reference in call_sites:
        callers[caller.qualified_name] = caller
        references.setdefault(caller.qualified_name, []).append(reference)
    return tuple(
        (callers[qualified_name], tuple(caller_references))
        for qualified_name, caller_references in references.items()
    )


def _caller_stays_within_budgets(
    symbol: SymbolIR,
    caller: SymbolIR,
    references: tuple[ReferenceIR, ...],
    settings: LowUseShortFunctionSettings,
) -> bool:
    call_count = len(references)
    return (
        caller.sloc + (_inline_sloc_delta(symbol) * call_count)
        <= settings.max_inline_caller_sloc
        and caller.cyc_complexity + (_inline_cyclomatic_delta(symbol) * call_count)
        <= settings.max_inline_caller_complexity
        and caller.cog_complexity + (symbol.cog_complexity * call_count)
        <= settings.max_inline_caller_cognitive_complexity
        and _projected_max_nesting(symbol, caller, references)
        <= settings.max_inline_call_nesting
    )


def _inline_sloc_delta(symbol: SymbolIR) -> int:
    return max(0, symbol.sloc - 1)


def _inline_cyclomatic_delta(symbol: SymbolIR) -> int:
    return max(0, symbol.cyc_complexity - 1)


def _projected_max_nesting(
    symbol: SymbolIR,
    caller: SymbolIR,
    references: tuple[ReferenceIR, ...],
) -> int:
    return max(
        caller.max_nesting,
        *(reference.nesting + symbol.max_nesting for reference in references),
    )


def _message(
    symbol: SymbolIR,
    call_sites: tuple[tuple[SymbolIR, ReferenceIR], ...],
) -> str:
    noun = "call site" if len(call_sites) == 1 else "call sites"
    return f"`{symbol.name}` is short and used at {len(call_sites)} {noun}; inline it"

"""Project-level semantic indexes and rule query helpers."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

from scb_check.tree_walking.models import EffectIR
from scb_check.tree_walking.models import EffectKind
from scb_check.tree_walking.models import ModuleIR
from scb_check.tree_walking.models import OperationIR
from scb_check.tree_walking.models import OperationKind
from scb_check.tree_walking.models import ProjectIR
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.models import SymbolRole
from scb_check.tree_walking.models import ValueIR
from scb_check.tree_walking.models import ValueKind

_RECEIVER_PARAMETER_NAMES = frozenset({"self", "cls"})
_REQUIRED_API_ROLES = frozenset(
    {
        SymbolRole.CONTRACT_MEMBER,
        SymbolRole.INHERITED_OVERRIDE,
        SymbolRole.COMPUTED_ATTRIBUTE,
        SymbolRole.ENTRYPOINT,
        SymbolRole.PUBLIC_API,
        SymbolRole.UNKNOWN_EXTERNAL_BINDING,
    },
)
_MEANINGFUL_RETURN_EFFECTS = frozenset(
    {
        EffectKind.EXTERNAL_CALL,
        EffectKind.MUTATION,
        EffectKind.RAISE,
        EffectKind.UNRESOLVED_CALL,
        EffectKind.WRITE,
    },
)


def build_project(modules: tuple[ModuleIR, ...]) -> ProjectIR:
    """Build project semantic indexes and derived effects from modules."""
    symbols = tuple(symbol for module in modules for symbol in module.symbols)
    symbols_by_qualified_name = {
        symbol.qualified_name: symbol for symbol in symbols
    }
    symbols_by_file = _symbols_by_file(symbols)
    module_name_by_file = {module.file: module.module_name for module in modules}
    effects_by_symbol = {
        symbol.qualified_name: _effects_for_symbol(
            symbol,
            symbols_by_qualified_name,
            module_name_by_file,
        )
        for symbol in symbols
        if symbol.kind in {SymbolKind.FUNCTION, SymbolKind.METHOD}
    }
    return ProjectIR(
        modules=modules,
        symbols_by_qualified_name=symbols_by_qualified_name,
        symbols_by_file=symbols_by_file,
        effects_by_symbol=effects_by_symbol,
    )


class RuleContext:
    """Language-agnostic semantic queries for structural rules."""

    def __init__(self, project: ProjectIR) -> None:
        """Initialize queries for `project`."""
        self.project = project
        self._module_name_by_file = {
            module.file: module.module_name for module in project.modules
        }

    def is_required_api_surface(self, symbol: SymbolIR) -> bool:
        """Return True when `symbol` has a semantic keep reason."""
        return bool(symbol.roles & _REQUIRED_API_ROLES)

    def is_inherited_override(self, symbol: SymbolIR) -> bool:
        """Return True when `symbol` implements an inherited contract."""
        return SymbolRole.INHERITED_OVERRIDE in symbol.roles

    def is_computed_attribute(self, symbol: SymbolIR) -> bool:
        """Return True when `symbol` exposes a computed attribute."""
        return SymbolRole.COMPUTED_ATTRIBUTE in symbol.roles

    def effects_for_symbol(self, symbol: SymbolIR) -> tuple[EffectIR, ...]:
        """Return derived effects for `symbol`."""
        return self.project.effects_by_symbol.get(symbol.qualified_name, ())

    def return_has_meaningful_effects(self, symbol: SymbolIR) -> bool:
        """Return True if the single returned value has meaningful effects."""
        return any(
            effect.kind in _MEANINGFUL_RETURN_EFFECTS
            for effect in self.effects_for_symbol(symbol)
        )

    def returns_forwarded_parameter(self, symbol: SymbolIR) -> bool:
        """Return True when `symbol` returns one of its own parameters."""
        value = _single_return_value(symbol)
        if value is None or value.kind is not ValueKind.SYMBOL_REFERENCE:
            return False
        return value.name in _forwardable_parameter_names(symbol)

    def returned_project_call_forwards_parameters(self, symbol: SymbolIR) -> bool:
        """Return True for pass-through calls to scanned project symbols."""
        value = _single_return_value(symbol)
        if value is None or value.kind is not ValueKind.INVOCATION:
            return False
        target = _resolve_project_value(
            value,
            symbol,
            self.project.symbols_by_qualified_name,
            self._module_name_by_file,
        )
        if target is None or target.qualified_name == symbol.qualified_name:
            return False
        argument_names = _argument_names(value)
        parameters = _forwardable_parameter_names(symbol)
        return bool(parameters) and argument_names == parameters

    def has_mutation(self, symbol: SymbolIR) -> bool:
        """Return True when derived effects include mutation."""
        return self._has_effect(symbol, EffectKind.MUTATION)

    def has_unresolved_call(self, symbol: SymbolIR) -> bool:
        """Return True when derived effects include unresolved calls."""
        return self._has_effect(symbol, EffectKind.UNRESOLVED_CALL)

    def _has_effect(self, symbol: SymbolIR, kind: EffectKind) -> bool:
        return any(effect.kind is kind for effect in self.effects_for_symbol(symbol))


def _symbols_by_file(symbols: tuple[SymbolIR, ...]) -> dict[Path, tuple[SymbolIR, ...]]:
    sorted_symbols = sorted(symbols, key=lambda symbol: symbol.file.as_posix())
    return {
        file_path: tuple(file_symbols)
        for file_path, file_symbols in groupby(
            sorted_symbols,
            key=lambda symbol: symbol.file,
        )
    }


def _effects_for_symbol(
    symbol: SymbolIR,
    symbols_by_qualified_name: dict[str, SymbolIR],
    module_name_by_file: dict[Path, str],
) -> tuple[EffectIR, ...]:
    effects: list[EffectIR] = []
    for operation in symbol.body:
        effects.extend(
            _effects_for_operation(
                symbol,
                operation,
                symbols_by_qualified_name,
                module_name_by_file,
            ),
        )
    return tuple(effects)


def _effects_for_operation(
    symbol: SymbolIR,
    operation: OperationIR,
    symbols_by_qualified_name: dict[str, SymbolIR],
    module_name_by_file: dict[Path, str],
) -> tuple[EffectIR, ...]:
    if operation.kind is OperationKind.RAISE:
        return (
            EffectIR(
                kind=EffectKind.RAISE,
                span=operation.span,
                symbol_qualified_name=symbol.qualified_name,
            ),
        )
    if operation.value is None:
        return ()
    return _effects_for_value(
        symbol,
        operation.value,
        symbols_by_qualified_name,
        module_name_by_file,
    )


def _effects_for_value(
    symbol: SymbolIR,
    value: ValueIR,
    symbols_by_qualified_name: dict[str, SymbolIR],
    module_name_by_file: dict[Path, str],
) -> tuple[EffectIR, ...]:
    child_effects = tuple(
        effect
        for argument in value.arguments
        for effect in _effects_for_value(
            symbol,
            argument,
            symbols_by_qualified_name,
            module_name_by_file,
        )
    )
    if value.kind is ValueKind.INVOCATION:
        target = _resolve_project_value(
            value,
            symbol,
            symbols_by_qualified_name,
            module_name_by_file,
        )
        if target is not None:
            call_effect = EffectIR(
                kind=EffectKind.PROJECT_CALL,
                span=value.span,
                symbol_qualified_name=symbol.qualified_name,
                target_name=value.name,
                target_qualified_name=target.qualified_name,
            )
        elif _is_external_call(value, symbol):
            call_effect = EffectIR(
                kind=EffectKind.EXTERNAL_CALL,
                span=value.span,
                symbol_qualified_name=symbol.qualified_name,
                target_name=value.name,
                target_qualified_name=value.resolved_name,
            )
        else:
            call_effect = EffectIR(
                kind=EffectKind.UNRESOLVED_CALL,
                span=value.span,
                symbol_qualified_name=symbol.qualified_name,
                target_name=value.name,
            )
        return (call_effect, *child_effects)
    if value.kind in {ValueKind.SYMBOL_REFERENCE, ValueKind.MEMBER_ACCESS}:
        return (
            EffectIR(
                kind=EffectKind.READ,
                span=value.span,
                symbol_qualified_name=symbol.qualified_name,
                target_name=value.name,
                target_qualified_name=value.resolved_name,
            ),
            *child_effects,
        )
    return child_effects


def _is_external_call(value: ValueIR, symbol: SymbolIR) -> bool:
    return (
        value.resolved_name is not None
        and value.resolved_name != value.name
    ) or (
        value.name is not None
        and "." in value.name
        and value.name.split(".", 1)[0] not in symbol.signature.parameters
    )


def _resolve_project_value(
    value: ValueIR,
    symbol: SymbolIR,
    symbols_by_qualified_name: dict[str, SymbolIR],
    module_name_by_file: dict[Path, str],
) -> SymbolIR | None:
    candidates = tuple(_candidate_qualified_names(value, symbol, module_name_by_file))
    return next(
        (
            symbols_by_qualified_name[candidate]
            for candidate in candidates
            if candidate in symbols_by_qualified_name
        ),
        None,
    )


def _candidate_qualified_names(
    value: ValueIR,
    symbol: SymbolIR,
    module_name_by_file: dict[Path, str],
) -> tuple[str, ...]:
    candidates: list[str] = []
    if value.resolved_name is not None:
        candidates.append(value.resolved_name)
    if value.name is not None and "." not in value.name:
        module_name = module_name_by_file.get(symbol.file)
        if module_name is not None:
            candidates.append(f"{module_name}.{value.name}")
    return tuple(dict.fromkeys(candidates))


def _single_return_value(symbol: SymbolIR) -> ValueIR | None:
    if len(symbol.body) != 1:
        return None
    operation = symbol.body[0]
    if operation.kind is not OperationKind.RETURN:
        return None
    return operation.value


def _forwardable_parameter_names(symbol: SymbolIR) -> frozenset[str]:
    parameters = frozenset(symbol.signature.parameters)
    if symbol.kind is SymbolKind.METHOD:
        return parameters - _RECEIVER_PARAMETER_NAMES
    return parameters


def _argument_names(value: ValueIR) -> frozenset[str]:
    names = {
        argument.name
        for argument in value.arguments
        if argument.kind is ValueKind.SYMBOL_REFERENCE and argument.name is not None
    }
    if len(names) != len(value.arguments):
        return frozenset()
    return frozenset(names)

"""Language-agnostic IR models for tree walking and structural rules."""

from __future__ import annotations

import math
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

HIGH_COMPLEXITY_THRESHOLD = 10


class IRModel(BaseModel):
    """Base for immutable Pydantic IR records."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class Language(StrEnum):
    """Supported source languages."""

    PYTHON = "python"
    PYTHON_STUB = "python-stub"


class Severity(StrEnum):
    """Structural finding severity."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SymbolKind(StrEnum):
    """Language-agnostic symbol categories."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VALUE = "value"


class SymbolRole(StrEnum):
    """Semantic roles used by structural rules."""

    CONTRACT_MEMBER = "contract-member"
    INHERITED_OVERRIDE = "inherited-override"
    COMPUTED_ATTRIBUTE = "computed-attribute"
    ENTRYPOINT = "entrypoint"
    PUBLIC_API = "public-api"
    FACTORY = "factory"
    UNKNOWN_EXTERNAL_BINDING = "unknown-external-binding"


class RuleTarget(StrEnum):
    """Subject category a structural rule checks."""

    SYMBOL = "symbol"
    MODULE = "module"
    OPERATION = "operation"
    PROJECT = "project"


class OperationKind(StrEnum):
    """Normalized body operation kinds."""

    RETURN = "return"
    BIND = "bind"
    ASSIGN = "assign"
    CALL = "call"
    BRANCH = "branch"
    LOOP = "loop"
    RAISE = "raise"
    YIELD = "yield"
    AWAIT = "await"
    ENTER_SCOPE = "enter-scope"
    UNKNOWN = "unknown"


class ValueKind(StrEnum):
    """Normalized expression value kinds."""

    SYMBOL_REFERENCE = "symbol-reference"
    MEMBER_ACCESS = "member-access"
    INVOCATION = "invocation"
    LITERAL = "literal"
    COLLECTION = "collection"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


class EffectKind(StrEnum):
    """Derived behavior facts used by semantic queries."""

    READ = "read"
    WRITE = "write"
    MUTATION = "mutation"
    PROJECT_CALL = "project-call"
    EXTERNAL_CALL = "external-call"
    ALLOCATION = "allocation"
    RAISE = "raise"
    UNRESOLVED_CALL = "unresolved-call"


class SourceSpan(IRModel):
    """A source range with 1-indexed lines and 0-indexed columns."""

    file: Path
    start_line: int = Field(ge=1)
    start_col: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_col: int = Field(ge=0)


class SignatureIR(IRModel):
    """Normalized callable signature facts."""

    parameters: tuple[str, ...] = ()
    annotations: dict[str, str | None] = Field(default_factory=dict)
    returns: str | None = None


class ImportIR(IRModel):
    """A module import binding."""

    local_name: str
    qualified_name: str
    span: SourceSpan


class ReferenceIR(IRModel):
    """A resolved symbol usage location in scanned source."""

    name: str
    resolved_name: str | None
    kind: Literal["call", "reference"]
    span: SourceSpan


class ValueIR(IRModel):
    """A normalized expression value."""

    kind: ValueKind
    span: SourceSpan
    text: str = ""
    name: str | None = None
    resolved_name: str | None = None
    arguments: tuple[ValueIR, ...] = ()


class OperationIR(IRModel):
    """A normalized statement or body operation."""

    kind: OperationKind
    span: SourceSpan
    value: ValueIR | None = None
    target: ValueIR | None = None


class EffectIR(IRModel):
    """A behavior fact derived from operations and semantic context."""

    kind: EffectKind
    span: SourceSpan
    symbol_qualified_name: str
    target_name: str | None = None
    target_qualified_name: str | None = None


class SymbolIR(IRModel):
    """A language-agnostic code symbol."""

    name: str
    qualified_name: str
    kind: SymbolKind
    span: SourceSpan
    language: Language = Language.PYTHON
    roles: frozenset[SymbolRole] = frozenset()
    signature: SignatureIR = Field(default_factory=SignatureIR)
    body: tuple[OperationIR, ...] = ()
    references: tuple[ReferenceIR, ...] = ()
    owner_qualified_name: str | None = None
    base_names: tuple[str, ...] = ()
    sloc: int = 0
    cyc_complexity: int = 1
    cog_complexity: int = 0

    @property
    def file(self) -> Path:
        """Return the source file for this symbol."""
        return self.span.file

    @property
    def start_line(self) -> int:
        """Return the 1-indexed starting line."""
        return self.span.start_line

    @property
    def end_line(self) -> int:
        """Return the 1-indexed ending line."""
        return self.span.end_line

    @property
    def return_operations(self) -> tuple[OperationIR, ...]:
        """Return normalized `return` operations in this symbol."""
        return tuple(
            operation
            for operation in self.body
            if operation.kind is OperationKind.RETURN
        )

    def cc_mass(self) -> float:
        """Return the cyclomatic complexity mass."""
        return self.cyc_complexity * math.sqrt(self.sloc)

    def cog_mass(self) -> float:
        """Return the cognitive complexity mass."""
        return self.cog_complexity * math.sqrt(self.sloc)

    def is_high_cc(self) -> bool:
        """Return True if the symbol exceeds the cyclomatic cutoff."""
        return self.cyc_complexity > HIGH_COMPLEXITY_THRESHOLD

    def is_high_cog(self) -> bool:
        """Return True if the symbol exceeds the cognitive cutoff."""
        return self.cog_complexity > HIGH_COMPLEXITY_THRESHOLD


class ModuleIR(IRModel):
    """A parsed source module with generic code facts."""

    language: Language
    file: Path
    module_name: str
    span: SourceSpan
    imports: tuple[ImportIR, ...] = ()
    symbols: tuple[SymbolIR, ...] = ()
    operations: tuple[OperationIR, ...] = ()
    references: tuple[ReferenceIR, ...] = ()
    sloc_lines: frozenset[int] = frozenset()


class ProjectIR(IRModel):
    """Project-level semantic indexes built from parsed modules."""

    modules: tuple[ModuleIR, ...]
    symbols_by_qualified_name: dict[str, SymbolIR]
    symbols_by_file: dict[Path, tuple[SymbolIR, ...]]
    effects_by_symbol: dict[str, tuple[EffectIR, ...]] = Field(default_factory=dict)


class RuleFinding(IRModel):
    """A structural rule finding."""

    rule_id: str
    severity: Severity
    message: str
    span: SourceSpan
    subject_name: str
    subject_qualified_name: str
    subject_kind: SymbolKind

    @property
    def file(self) -> Path:
        """Return the source file for this finding."""
        return self.span.file

    @property
    def start_line(self) -> int:
        """Return the 1-indexed starting line."""
        return self.span.start_line

    @property
    def end_line(self) -> int:
        """Return the 1-indexed ending line."""
        return self.span.end_line

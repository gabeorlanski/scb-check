"""Shared immutable models for analysis and reporting."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

HIGH_COMPLEXITY_THRESHOLD = 10


@dataclass(frozen=True, slots=True)
class CloneBlock:
    """A duplicated syntax block found in one file."""

    file: Path
    start_line: int
    end_line: int
    group_hash: str
    instance_count: int
    other_instances: tuple[tuple[Path, int], ...]
    first_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AstGrepHit:
    """An ast-grep rule match with source location and message."""

    file: Path
    line: int
    end_line: int
    col: int
    end_col: int
    rule_id: str
    matched_text: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class SymbolUsage:
    """A resolved symbol usage location in scanned source."""

    file: Path
    line: int
    col: int
    name: str
    resolved_name: str | None
    kind: Literal["call", "reference"]


@dataclass(frozen=True, slots=True)
class TrivialWrapper:
    """A trivial wrapper or alias with resolved usage locations."""

    file: Path
    start_line: int
    end_line: int
    col: int
    end_col: int
    name: str
    qualified_name: str
    kind: Literal["single_return_function", "function_alias"]
    usages: tuple[SymbolUsage, ...] = field(default_factory=tuple)

    @property
    def usage_count(self) -> int:  # scbc ignore[trivial-wrapper] Public convenience property.
        """Return the number of resolved usages."""
        return len(self.usages)


class ParsedSymbol(BaseModel):
    """A parsed function-like symbol with complexity and usage metadata."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    file: Path
    start: tuple[int, int]
    end: tuple[int, int]
    node_type: str
    statements: int
    sloc: int
    cyc_complexity: int
    cog_complexity: int
    agruments: dict[str, str | None] = Field(default_factory=dict)
    returns: str | None = None
    usages: tuple[SymbolUsage, ...] = Field(default_factory=tuple)

    @property
    def arguments(self) -> dict[str, str | None]:  # scbc ignore[trivial-wrapper] Compatibility alias for misspelled field.
        """Return parsed argument annotations."""
        return self.agruments

    @property
    def start_line(self) -> int:  # scbc ignore[trivial-wrapper] Public convenience property.
        """Return the 1-indexed starting line."""
        return self.start[0]

    @property
    def end_line(self) -> int:  # scbc ignore[trivial-wrapper] Public convenience property.
        """Return the 1-indexed ending line."""
        return self.end[0]

    def cc_mass(self) -> float:  # scbc ignore[trivial-wrapper] Public metric helper.
        """Return the cyclomatic complexity mass."""
        return self.cyc_complexity * math.sqrt(self.sloc)

    def cog_mass(self) -> float:  # scbc ignore[trivial-wrapper] Public metric helper.
        """Return the cognitive complexity mass."""
        return self.cog_complexity * math.sqrt(self.sloc)

    def is_high_cc(self) -> bool:  # scbc ignore[trivial-wrapper] Public metric predicate.
        """Return True if the function is high cyclomatic complexity."""
        return self.cyc_complexity > HIGH_COMPLEXITY_THRESHOLD

    def is_high_cog(self) -> bool:  # scbc ignore[trivial-wrapper] Public metric predicate.
        """Return True if the function is high cognitive complexity."""
        return self.cog_complexity > HIGH_COMPLEXITY_THRESHOLD


@dataclass(frozen=True, slots=True)
class FileLineSet:
    """A file path paired with immutable 1-indexed line numbers."""

    file: Path
    lines: frozenset[int]

    @classmethod
    def from_parts(cls, file: Path, lines: Iterable[int]) -> FileLineSet:  # scbc ignore[trivial-wrapper] Public coercing constructor.
        """Build a `FileLineSet` from any iterable of line numbers."""
        return cls(file=file, lines=frozenset(lines))


@dataclass(frozen=True, slots=True)
class Flags:
    """Sorted analysis findings and line sets used for reporting."""

    clones: tuple[CloneBlock, ...] = field(default_factory=tuple)
    ast_grep_hits: tuple[AstGrepHit, ...] = field(default_factory=tuple)
    trivial_wrappers: tuple[TrivialWrapper, ...] = field(default_factory=tuple)
    high_cc_functions: tuple[ParsedSymbol, ...] = field(default_factory=tuple)
    high_cog_functions: tuple[ParsedSymbol, ...] = field(default_factory=tuple)
    total_loc_by_file: tuple[tuple[Path, int], ...] = field(
        default_factory=tuple,
    )
    all_functions: tuple[ParsedSymbol, ...] = field(default_factory=tuple)
    clone_sloc_lines_by_file: tuple[FileLineSet, ...] = field(
        default_factory=tuple,
    )
    ast_sloc_lines_by_file: tuple[FileLineSet, ...] = field(
        default_factory=tuple,
    )
    trivial_wrapper_sloc_lines_by_file: tuple[FileLineSet, ...] = field(
        default_factory=tuple,
    )

    @classmethod
    def from_parts(  # noqa: PLR0913
        cls,
        *,
        clones: Iterable[CloneBlock] = (),
        ast_grep_hits: Iterable[AstGrepHit] = (),
        trivial_wrappers: Iterable[TrivialWrapper] = (),
        high_cc_functions: Iterable[ParsedSymbol] = (),
        high_cog_functions: Iterable[ParsedSymbol] = (),
        total_loc_by_file: Iterable[tuple[Path, int]] = (),
        all_functions: Iterable[ParsedSymbol] = (),
        clone_sloc_lines_by_file: Iterable[
            FileLineSet | tuple[Path, Iterable[int]]
        ] = (),
        ast_sloc_lines_by_file: Iterable[
            FileLineSet | tuple[Path, Iterable[int]]
        ] = (),
        trivial_wrapper_sloc_lines_by_file: Iterable[
            FileLineSet | tuple[Path, Iterable[int]]
        ] = (),
    ) -> Flags:
        """Build `Flags` while coercing iterable inputs to tuple fields."""
        clone_lines = _coerce_file_line_sets(clone_sloc_lines_by_file)
        ast_lines = _coerce_file_line_sets(ast_sloc_lines_by_file)
        trivial_wrapper_lines = _coerce_file_line_sets(
            trivial_wrapper_sloc_lines_by_file,
        )
        return cls(
            clones=tuple(clones),
            ast_grep_hits=tuple(ast_grep_hits),
            trivial_wrappers=tuple(trivial_wrappers),
            high_cc_functions=tuple(high_cc_functions),
            high_cog_functions=tuple(high_cog_functions),
            total_loc_by_file=tuple(total_loc_by_file),
            all_functions=tuple(all_functions),
            clone_sloc_lines_by_file=clone_lines,
            ast_sloc_lines_by_file=ast_lines,
            trivial_wrapper_sloc_lines_by_file=trivial_wrapper_lines,
        )


@dataclass(frozen=True, slots=True)
class Report:
    """Computed verbosity and erosion summary for JSON output."""

    verbosity: float
    erosion: float
    cog_erosion: float
    files_scanned: int
    total_loc: int
    verbosity_flagged_loc: int
    clone_loc: int
    ast_grep_flagged_loc: int
    trivial_wrapper_loc: int
    trivial_wrappers: int
    total_functions: int
    high_cc_functions: int
    high_cog_functions: int
    total_mass: float
    high_cc_mass: float
    total_cog_mass: float
    high_cog_mass: float


# scbc ignore[trivial-wrapper] Names shared coercion for each line-set field.
def _coerce_file_line_sets(
    values: Iterable[FileLineSet | tuple[Path, Iterable[int]]],
) -> tuple[FileLineSet, ...]:
    return tuple(_coerce_file_line_set(value) for value in values)


def _coerce_file_line_set(
    value: FileLineSet | tuple[Path, Iterable[int]],
) -> FileLineSet:
    if isinstance(value, FileLineSet):
        return value
    path, lines = value
    return FileLineSet.from_parts(path, lines)

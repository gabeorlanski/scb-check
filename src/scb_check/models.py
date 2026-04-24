"""Shared immutable models for analysis and reporting."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

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


class ParsedSymbol(BaseModel):
    """A parsed function-like symbol with complexity and call metadata."""

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
    calls: Counter[str] = Field(default_factory=Counter)

    @property
    def arguments(self) -> dict[str, str | None]:
        """Return parsed argument annotations."""
        return self.agruments

    @property
    def start_line(self) -> int:
        """Return the 1-indexed starting line."""
        return self.start[0]

    @property
    def end_line(self) -> int:
        """Return the 1-indexed ending line."""
        return self.end[0]

    def cc_mass(self) -> float:
        """Return the cyclomatic complexity mass."""
        return self.cyc_complexity * math.sqrt(self.sloc)

    def cog_mass(self) -> float:
        """Return the cognitive complexity mass."""
        return self.cog_complexity * math.sqrt(self.sloc)

    def is_high_cc(self) -> bool:
        """Return True if the function is high cyclomatic complexity."""
        return self.cyc_complexity > HIGH_COMPLEXITY_THRESHOLD

    def is_high_cog(self) -> bool:
        """Return True if the function is high cognitive complexity."""
        return self.cog_complexity > HIGH_COMPLEXITY_THRESHOLD


@dataclass(frozen=True, slots=True)
class FileLineSet:
    """A file path paired with immutable 1-indexed line numbers."""

    file: Path
    lines: frozenset[int]

    @classmethod
    def from_parts(cls, file: Path, lines: Iterable[int]) -> FileLineSet:
        """Build a `FileLineSet` from any iterable of line numbers."""
        return cls(file=file, lines=frozenset(lines))


@dataclass(frozen=True, slots=True)
class Flags:
    """Sorted analysis findings and line sets used for reporting."""

    clones: tuple[CloneBlock, ...] = field(default_factory=tuple)
    ast_grep_hits: tuple[AstGrepHit, ...] = field(default_factory=tuple)
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

    @classmethod
    def from_parts(  # noqa: PLR0913
        cls,
        *,
        clones: Iterable[CloneBlock] = (),
        ast_grep_hits: Iterable[AstGrepHit] = (),
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
    ) -> Flags:
        """Build `Flags` while coercing iterable inputs to tuple fields."""
        return cls(
            clones=tuple(clones),
            ast_grep_hits=tuple(ast_grep_hits),
            high_cc_functions=tuple(high_cc_functions),
            high_cog_functions=tuple(high_cog_functions),
            total_loc_by_file=tuple(total_loc_by_file),
            all_functions=tuple(all_functions),
            clone_sloc_lines_by_file=_coerce_file_line_sets(
                clone_sloc_lines_by_file,
            ),
            ast_sloc_lines_by_file=_coerce_file_line_sets(
                ast_sloc_lines_by_file,
            ),
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
    total_functions: int
    high_cc_functions: int
    high_cog_functions: int
    total_mass: float
    high_cc_mass: float
    total_cog_mass: float
    high_cog_mass: float


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

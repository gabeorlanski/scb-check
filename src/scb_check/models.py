from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CloneBlock:
    file: Path
    start_line: int
    end_line: int
    group_hash: str
    instance_count: int
    other_instances: tuple[tuple[Path, int], ...]
    first_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AstGrepHit:
    file: Path
    line: int
    end_line: int
    col: int
    end_col: int
    rule_id: str
    matched_text: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class FunctionSymbol:
    file: Path
    name: str
    start_line: int
    end_line: int
    complexity: int
    sloc: int


@dataclass(frozen=True, slots=True)
class FileLineSet:
    file: Path
    lines: frozenset[int]

    @classmethod
    def from_parts(cls, file: Path, lines: Iterable[int]) -> FileLineSet:
        return cls(file=file, lines=frozenset(lines))


@dataclass(frozen=True, slots=True)
class Flags:
    clones: tuple[CloneBlock, ...] = field(default_factory=tuple)
    ast_grep_hits: tuple[AstGrepHit, ...] = field(default_factory=tuple)
    high_cc_functions: tuple[FunctionSymbol, ...] = field(default_factory=tuple)
    total_loc_by_file: tuple[tuple[Path, int], ...] = field(
        default_factory=tuple
    )
    all_functions: tuple[FunctionSymbol, ...] = field(default_factory=tuple)
    clone_sloc_lines_by_file: tuple[FileLineSet, ...] = field(
        default_factory=tuple
    )
    ast_grep_sloc_lines_by_file: tuple[FileLineSet, ...] = field(
        default_factory=tuple
    )

    @classmethod
    def from_parts(
        cls,
        *,
        clones: Iterable[CloneBlock] = (),
        ast_grep_hits: Iterable[AstGrepHit] = (),
        high_cc_functions: Iterable[FunctionSymbol] = (),
        total_loc_by_file: Iterable[tuple[Path, int]] = (),
        all_functions: Iterable[FunctionSymbol] = (),
        clone_sloc_lines_by_file: Iterable[
            FileLineSet | tuple[Path, Iterable[int]]
        ] = (),
        ast_grep_sloc_lines_by_file: Iterable[
            FileLineSet | tuple[Path, Iterable[int]]
        ] = (),
    ) -> Flags:
        return cls(
            clones=tuple(clones),
            ast_grep_hits=tuple(ast_grep_hits),
            high_cc_functions=tuple(high_cc_functions),
            total_loc_by_file=tuple(total_loc_by_file),
            all_functions=tuple(all_functions),
            clone_sloc_lines_by_file=_coerce_file_line_sets(
                clone_sloc_lines_by_file
            ),
            ast_grep_sloc_lines_by_file=_coerce_file_line_sets(
                ast_grep_sloc_lines_by_file
            ),
        )


@dataclass(frozen=True, slots=True)
class Report:
    verbosity: float
    erosion: float
    files_scanned: int
    total_loc: int
    verbosity_flagged_loc: int
    clone_loc: int
    ast_grep_flagged_loc: int
    total_functions: int
    high_cc_functions: int
    total_mass: float
    high_cc_mass: float


def _coerce_file_line_sets(
    values: Iterable[FileLineSet | tuple[Path, Iterable[int]]],
) -> tuple[FileLineSet, ...]:
    normalized: list[FileLineSet] = []
    for value in values:
        if isinstance(value, FileLineSet):
            normalized.append(value)
            continue
        path, lines = value
        normalized.append(FileLineSet.from_parts(path, lines))
    return tuple(normalized)

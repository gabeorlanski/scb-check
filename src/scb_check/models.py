"""Shared immutable models for analysis and reporting."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Literal

from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import SymbolIR

type AstGrepSeverity = Literal["info", "warning", "critical"]
type ReportValue = int | float | dict[str, dict[str, int]]


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
    severity: AstGrepSeverity = "warning"


@dataclass(frozen=True, slots=True)
class FileLineSet:
    """A file path paired with immutable 1-indexed line numbers."""

    file: Path
    lines: frozenset[int]

    @classmethod
    def from_parts(cls, file: Path, lines: Iterable[int]) -> FileLineSet:
        """Build a `FileLineSet` from line numbers."""
        return cls(file=file, lines=frozenset(lines))


@dataclass(frozen=True, slots=True)
class FindingGroups:
    """Analysis findings grouped by source."""

    clones: tuple[CloneBlock, ...] = ()
    ast_grep_hits: tuple[AstGrepHit, ...] = ()
    structural_findings: tuple[RuleFinding, ...] = ()
    high_cc_functions: tuple[SymbolIR, ...] = ()
    high_cog_functions: tuple[SymbolIR, ...] = ()
    all_functions: tuple[SymbolIR, ...] = ()


@dataclass(frozen=True, slots=True)
class LineGroups:
    """SLOC line sets used for scoring."""

    total_loc_by_file: tuple[tuple[Path, int], ...] = ()
    clone_sloc_lines_by_file: tuple[FileLineSet, ...] = ()
    ast_sloc_lines_by_file: tuple[FileLineSet, ...] = ()
    structural_sloc_lines_by_file: tuple[FileLineSet, ...] = ()


@dataclass(frozen=True, slots=True)
class LanguageSyntaxSummary:
    """Syntax tree and node counts for one source language."""

    language: Language
    tree_count: int
    node_count: int


@dataclass(frozen=True, slots=True)
class Flags:
    """Sorted analysis findings and line sets used for reporting."""

    findings: FindingGroups = field(default_factory=FindingGroups)
    lines: LineGroups = field(default_factory=LineGroups)
    syntax_by_language: tuple[LanguageSyntaxSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportScores:
    """Top-level score values."""

    verbosity: float
    erosion: float
    cog_erosion: float


@dataclass(frozen=True, slots=True)
class VerbositySummary:
    """Verbosity line-count summary."""

    files_scanned: int
    total_loc: int
    verbosity_flagged_loc: int
    clone_loc: int
    ast_grep_flagged_loc: int
    structural_rule_loc: int
    structural_rule_findings: int


@dataclass(frozen=True, slots=True)
class FunctionMassSummary:
    """Function count and mass summary for erosion metrics."""

    total_functions: int
    high_cc_functions: int
    high_cog_functions: int
    total_mass: float
    high_cc_mass: float
    total_cog_mass: float
    high_cog_mass: float


@dataclass(frozen=True, slots=True)
class Report:
    """Computed verbosity and erosion summary for JSON output."""

    scores: ReportScores
    verbosity_summary: VerbositySummary
    function_summary: FunctionMassSummary
    syntax_by_language: tuple[LanguageSyntaxSummary, ...] = ()

    @property
    def syntax_tree_count(self) -> int:
        """Return the total parsed syntax tree count."""
        return sum(summary.tree_count for summary in self.syntax_by_language)

    @property
    def syntax_node_count(self) -> int:
        """Return the total syntax node count."""
        return sum(summary.node_count for summary in self.syntax_by_language)

    def to_dict(self) -> dict[str, ReportValue]:
        """Return the JSON-compatible report payload."""
        return {
            "verbosity": self.scores.verbosity,
            "erosion": self.scores.erosion,
            "cog_erosion": self.scores.cog_erosion,
            "files_scanned": self.verbosity_summary.files_scanned,
            "total_loc": self.verbosity_summary.total_loc,
            "verbosity_flagged_loc": self.verbosity_summary.verbosity_flagged_loc,
            "clone_loc": self.verbosity_summary.clone_loc,
            "ast_grep_flagged_loc": self.verbosity_summary.ast_grep_flagged_loc,
            "structural_rule_loc": self.verbosity_summary.structural_rule_loc,
            "structural_rule_findings": self.verbosity_summary.structural_rule_findings,
            "total_functions": self.function_summary.total_functions,
            "high_cc_functions": self.function_summary.high_cc_functions,
            "high_cog_functions": self.function_summary.high_cog_functions,
            "total_mass": self.function_summary.total_mass,
            "high_cc_mass": self.function_summary.high_cc_mass,
            "total_cog_mass": self.function_summary.total_cog_mass,
            "high_cog_mass": self.function_summary.high_cog_mass,
            "syntax_tree_count": self.syntax_tree_count,
            "syntax_node_count": self.syntax_node_count,
            "syntax_by_language": {
                summary.language.value: {
                    "tree_count": summary.tree_count,
                    "node_count": summary.node_count,
                }
                for summary in self.syntax_by_language
            },
        }

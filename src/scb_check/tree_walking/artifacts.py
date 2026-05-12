"""Parser artifacts and dispatch exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import ModuleIR


class TreeWalkingError(ValueError):
    """Base error carrying optional parse context."""

    def __init__(
        self,
        message: str,
        *,
        language: Language | None = None,
        file_path: Path | None = None,
    ) -> None:
        """Initialize with `message` and optional source context."""
        super().__init__(message)
        self.language = language
        self.file_path = file_path


class LanguageParseError(TreeWalkingError):
    """Raised when one language parser cannot parse supplied source."""

    @property
    def parser_language(self) -> Language | None:
        """Return the parser language that failed, when known."""
        return self.language


class ProjectParseError(TreeWalkingError):
    """Raised when dispatch cannot parse a project file."""

    @property
    def source_file(self) -> Path | None:
        """Return the project file that failed, when known."""
        return self.file_path


@dataclass(frozen=True, slots=True)
class ParsedFile:
    """Parsed source plus pure IR and parser-native clone data."""

    file: Path
    source: str
    module: ModuleIR
    native_tree: object | None = None

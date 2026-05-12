"""Language parser dispatch for already-read source files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from scb_check.tree_walking.artifacts import LanguageParseError
from scb_check.tree_walking.artifacts import ParsedFile
from scb_check.tree_walking.artifacts import ProjectParseError
from scb_check.tree_walking.languages.python import PythonParser
from scb_check.tree_walking.models import Language


class LanguageParser(Protocol):
    """Parser interface for one language."""

    language: Language

    def parse(self, file_path: Path, source: str) -> ParsedFile:
        """Parse already-read `source` for `file_path`."""


ExtensionLanguages = Mapping[str, tuple[Language, ...]]
ParserRegistry = Mapping[Language, LanguageParser]

DEFAULT_EXTENSION_LANGUAGES: ExtensionLanguages = {
    ".py": (Language.PYTHON,),
    ".pyw": (Language.PYTHON,),
}
_DEFAULT_PYTHON_PARSER = PythonParser()
_DEFAULT_PARSERS: ParserRegistry = {_DEFAULT_PYTHON_PARSER.language: _DEFAULT_PYTHON_PARSER}


def parse_source_file(
    file_path: Path,
    source: str,
    *,
    language_filter: frozenset[Language] | None = None,
) -> ParsedFile:
    """Parse already-read `source` for `file_path` using default dispatch."""
    return dispatch_parse(
        file_path,
        source,
        language_filter=language_filter,
    )


def dispatch_parse(
    file_path: Path,
    source: str,
    *,
    language_filter: frozenset[Language] | None = None,
    extension_languages: ExtensionLanguages = DEFAULT_EXTENSION_LANGUAGES,
    parsers: ParserRegistry = _DEFAULT_PARSERS,
) -> ParsedFile:
    """Dispatch parsing by extension and optional language filter."""
    candidates = _candidate_languages(
        file_path,
        extension_languages,
        language_filter,
    )
    if not candidates:
        raise ProjectParseError(
            f"no parser candidates for `{file_path}`",
            file_path=file_path,
        )

    failures: list[LanguageParseError] = []
    for language in candidates:
        if language not in parsers:
            continue
        parser = parsers[language]
        try:
            return parser.parse(file_path, source)
        except LanguageParseError as exc:
            failures.append(exc)

    if failures:
        languages = ", ".join(language.value for language in candidates)
        raise ProjectParseError(
            f"failed to parse `{file_path}` as {languages}",
            file_path=file_path,
        ) from failures[-1]
    raise ProjectParseError(
        f"no parser candidates for `{file_path}`",
        file_path=file_path,
    )


def _candidate_languages(
    file_path: Path,
    extension_languages: ExtensionLanguages,
    language_filter: frozenset[Language] | None,
) -> tuple[Language, ...]:
    candidates = extension_languages.get(file_path.suffix.lower(), ())
    if language_filter is None:
        return candidates
    return tuple(language for language in candidates if language in language_filter)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from scb_check.tree_walking.dispatch import LanguageParseError
from scb_check.tree_walking.dispatch import ParsedFile
from scb_check.tree_walking.dispatch import ProjectParseError
from scb_check.tree_walking.dispatch import dispatch_parse
from scb_check.tree_walking.dispatch import parse_source_file
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import ModuleIR
from scb_check.tree_walking.models import SourceSpan


@dataclass(frozen=True, slots=True)
class FailingParser:
    """Test parser that always fails."""

    language: Language

    def parse(self, file_path: Path, source: str) -> ParsedFile:
        """Raise a parse failure."""
        del file_path, source
        raise LanguageParseError("cannot parse as fake language")


@dataclass(frozen=True, slots=True)
class SuccessfulParser:
    """Test parser that returns a minimal parsed file."""

    language: Language

    def parse(self, file_path: Path, source: str) -> ParsedFile:
        """Return a parsed file for dispatch tests."""
        return ParsedFile(
            file=file_path,
            source=source,
            module=ModuleIR(
                language=self.language,
                file=file_path,
                module_name=file_path.stem,
                span=SourceSpan(
                    file=file_path,
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=0,
                ),
            ),
        )


def test_dispatch_parses_python_from_source(tmp_path: Path) -> None:
    """Default dispatch parses already-read Python source."""
    file_path = tmp_path / "sample.py"

    parsed = parse_source_file(file_path, "value = 1\n")

    assert parsed.module.language is Language.PYTHON
    assert parsed.module.file == file_path
    assert parsed.source == "value = 1\n"


def test_dispatch_falls_back_to_later_candidate(tmp_path: Path) -> None:
    """Dispatch tries later language candidates when an earlier parser fails."""
    file_path = tmp_path / "sample.code"

    parsed = dispatch_parse(
        file_path,
        "value = 1\n",
        extension_languages={".code": (Language.PYTHON_STUB, Language.PYTHON)},
        parsers={
            Language.PYTHON_STUB: FailingParser(Language.PYTHON_STUB),
            Language.PYTHON: SuccessfulParser(Language.PYTHON),
        },
    )

    assert parsed.module.language is Language.PYTHON


def test_dispatch_applies_language_filter(tmp_path: Path) -> None:
    """Configured language filters remove non-selected candidates."""
    file_path = tmp_path / "sample.py"

    with pytest.raises(ProjectParseError, match="no parser candidates") as exc_info:
        dispatch_parse(
            file_path,
            "value = 1\n",
            language_filter=frozenset({Language.PYTHON_STUB}),
        )

    assert exc_info.value.source_file == file_path


def test_dispatch_wraps_syntax_failures(tmp_path: Path) -> None:
    """Parser syntax failures are exposed as project parse errors."""
    file_path = tmp_path / "broken.py"

    with pytest.raises(ProjectParseError, match="failed to parse") as exc_info:
        parse_source_file(file_path, "def broken(:\n    return 1\n")

    assert exc_info.value.source_file == file_path
    assert isinstance(exc_info.value.__cause__, LanguageParseError)
    assert exc_info.value.__cause__.parser_language is Language.PYTHON

"""Load bundled and extra ast-grep rule resources."""

from __future__ import annotations

import os
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import yaml

_RULES_PACKAGE = "scb_check.resources"
_RULES_DIR_NAME = "slop_rules"
_EXTRA_RULES_ENV = "SCB_CHECK_EXTRA_SLOP_RULES"
type RuleSeverity = Literal["info", "warning", "critical"]
type RuleDocument = dict[str, object]


def _rule_file_names() -> tuple[str, ...]:
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    return tuple(
        sorted(
            entry.name
            for entry in rules_dir.iterdir()
            if entry.name.endswith(".yaml")
        ),
    )


def _env_rules() -> tuple[Path, ...]:
    raw_paths = os.environ.get(_EXTRA_RULES_ENV, "")
    if not raw_paths.strip():
        return ()

    paths: list[Path] = []
    for raw_path in raw_paths.split(os.pathsep):
        clean_path = raw_path.strip()
        if not clean_path:
            continue

        path = Path(clean_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        paths.append(path)

    return tuple(paths)


def _extra_rules() -> tuple[Path, ...]:
    candidates = _env_rules()

    existing: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        existing.append(resolved)

    return tuple(existing)


def rule_texts() -> Iterator[tuple[str, str]]:
    """Yield bundled and environment-provided ast-grep rule text."""
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    for name in _rule_file_names():
        yield name, rules_dir.joinpath(name).read_text(encoding="utf-8")

    for path in _extra_rules():
        yield path.name, path.read_text(encoding="utf-8")


def find_rule_document(rule_id: str) -> RuleDocument | None:
    """Return the first active ast-grep rule document matching `rule_id`."""
    return next(
        (
            document
            for _, text in rule_texts()
            for document in _rule_documents_from_text(text)
            if document.get("id") == rule_id
        ),
        None,
    )


def load_rule_ids(rules_path: Path) -> frozenset[str]:
    """Load ast-grep rule IDs from `rules_path`."""
    return frozenset(
        rule_id
        for document in _rule_documents(rules_path)
        for rule_id in [document.get("id")]
        if isinstance(rule_id, str)
    )


def load_thresholds(rules_path: Path) -> dict[str, int]:
    """Load per-rule minimum file-count thresholds from `rules_path`."""
    return _load_rule_entries(rules_path, _threshold)


def load_rule_severities(rules_path: Path) -> dict[str, RuleSeverity]:
    """Load ast-grep rule severities from `rules_path`."""
    return _load_rule_entries(rules_path, _severity)


def _load_rule_entries[T](
    rules_path: Path,
    extractor: Callable[[RuleDocument], tuple[str, T] | None],
) -> dict[str, T]:
    return dict(
        entry
        for document in _rule_documents(rules_path)
        if (entry := extractor(document)) is not None
    )


def _rule_documents(rules_path: Path) -> tuple[RuleDocument, ...]:
    with rules_path.open("r", encoding="utf-8") as rules_file:
        return tuple(_normalized_rule_documents(yaml.safe_load_all(rules_file)))


def _rule_documents_from_text(text: str) -> tuple[RuleDocument, ...]:
    return tuple(_normalized_rule_documents(yaml.safe_load_all(text)))


def _normalized_rule_documents(documents: Iterator[object]) -> Iterator[RuleDocument]:
    for document in documents:
        normalized = _rule_document(document)
        if normalized is not None:
            yield normalized


def _rule_document(document: object) -> RuleDocument | None:  # scbc ignore[object-type-annotation]
    # scbc boundary: normalize rule metadata loaded from YAML.
    if not isinstance(document, Mapping):
        return None
    return {
        key: value
        for key, value in document.items()
        if isinstance(key, str)
    }


def _severity(document: RuleDocument) -> tuple[str, RuleSeverity] | None:
    rule_id = document.get("id")
    severity = _rule_severity(document.get("severity"))
    if isinstance(rule_id, str) and severity is not None:
        return (rule_id, severity)
    return None


def _rule_severity(value: object) -> RuleSeverity | None:  # scbc ignore[object-type-annotation]
    match value:
        case "info":
            return "info"
        case "warning":
            return "warning"
        case "critical":
            return "critical"
        case _:
            return None


def _threshold(document: RuleDocument) -> tuple[str, int] | None:
    rule_id = document.get("id")
    metadata = _rule_document(document.get("metadata"))
    if not isinstance(rule_id, str) or metadata is None:
        return None

    min_count = metadata.get("min_file_count")
    if isinstance(min_count, int) and min_count > 1:
        return (rule_id, min_count)
    return None


@contextmanager
def rules_file() -> Iterator[Path]:
    """Write all active ast-grep rules to a temporary YAML file."""
    with NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        for _, text in rule_texts():
            tmp.write(text)
            if not text.endswith("\n"):
                tmp.write("\n")
        tmp_path = Path(tmp.name)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)

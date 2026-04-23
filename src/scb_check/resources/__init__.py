from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

_RULES_PACKAGE = "scb_check.resources"
_RULES_DIR_NAME = "slop_rules"
_EXTRA_RULES_ENV = "SCB_CHECK_EXTRA_SLOP_RULES"


def _rule_file_names() -> tuple[str, ...]:
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    return tuple(
        sorted(
            entry.name
            for entry in rules_dir.iterdir()
            if entry.name.endswith(".yaml")
        )
    )


def _extra_rule_paths_from_env() -> tuple[Path, ...]:
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


def _existing_extra_rule_paths() -> tuple[Path, ...]:
    candidates = _extra_rule_paths_from_env()

    existing: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        if not resolved.is_file():
            continue

        seen.add(resolved)
        existing.append(resolved)

    return tuple(existing)


def iter_slop_rule_texts() -> Iterator[tuple[str, str]]:
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    for name in _rule_file_names():
        yield name, rules_dir.joinpath(name).read_text(encoding="utf-8")

    for path in _existing_extra_rule_paths():
        yield path.name, path.read_text(encoding="utf-8")


def load_min_file_count_thresholds(rules_path: Path) -> dict[str, int]:
    with rules_path.open("r", encoding="utf-8") as rules_file:
        documents = tuple(yaml.safe_load_all(rules_file))

    thresholds: dict[str, int] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        rule_id = document.get("id")
        metadata = document.get("metadata")
        if not isinstance(rule_id, str) or not isinstance(metadata, dict):
            continue
        min_count = metadata.get("min_file_count")
        if isinstance(min_count, int) and min_count > 1:
            thresholds[rule_id] = min_count
    return thresholds


@contextmanager
def combined_slop_rules_file() -> Iterator[Path]:
    with NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        for _, text in iter_slop_rule_texts():
            tmp.write(text)
            if not text.endswith("\n"):
                tmp.write("\n")
        tmp_path = Path(tmp.name)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)

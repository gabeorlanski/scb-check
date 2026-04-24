"""Discover Python files while applying configured excludes."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from pathlib import Path

from scb_check.config import Config

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
    },
)


def walk_python_files(path: Path, config: Config) -> Iterator[Path]:
    """Yield Python files under `path` after applying `config` excludes."""
    if not path.exists():
        raise FileNotFoundError(f"path does not exist: {path}")

    if path.is_file():
        if path.suffix != ".py":
            raise ValueError(f"not a Python file: {path}")
        yield path.resolve()
        return

    yield from _walk_directory(path.resolve(), config)


def _walk_directory(root: Path, config: Config) -> Iterator[Path]:
    for child in root.iterdir():
        is_symlink = child.is_symlink()
        if is_symlink or child.is_dir():
            if not is_symlink and child.name not in DEFAULT_EXCLUDED_DIRS:
                yield from _walk_directory(child, config)
            continue

        if child.suffix == ".py" and not _is_user_excluded(child, config):
            yield child.resolve()


def _is_user_excluded(path: Path, config: Config) -> bool:
    try:
        rel_path = path.relative_to(config.base_dir).as_posix()
    except ValueError:
        rel_path = path.resolve().as_posix()
    path_parts = tuple(part for part in rel_path.split("/") if part)
    return bool(config.exclude) and any(
        _match_pattern(path_parts, pattern) for pattern in config.exclude
    )


def _match_pattern(path_parts: tuple[str, ...], pattern: str) -> bool:
    pattern_parts = tuple(part for part in pattern.split("/") if part)
    return _match_segments(path_parts, pattern_parts)


def _match_segments(
    path_parts: tuple[str, ...],
    pattern_parts: tuple[str, ...],
) -> bool:
    if not pattern_parts:
        return not path_parts

    head = pattern_parts[0]
    tail = pattern_parts[1:]

    if head == "**":
        return any(
            _match_segments(path_parts[index:], tail)
            for index in range(len(path_parts) + 1)
        )

    return (
        path_parts != ()
        and fnmatch.fnmatch(path_parts[0], head)
        and _match_segments(path_parts[1:], tail)
    )

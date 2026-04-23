from __future__ import annotations

import fnmatch
import os
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
    }
)


class PathError(ValueError):
    pass


def discover_python_files(path: Path, config: Config) -> tuple[Path, ...]:
    if not path.exists():
        raise PathError(f"path does not exist: {path}")

    if path.is_file():
        if path.suffix != ".py":
            raise PathError(f"not a Python file: {path}")
        return (path.resolve(),)

    files = _discover_from_directory(path.resolve(), config)
    if not files:
        raise PathError(f"no Python files found at {path}")
    return tuple(sorted(files))


def _discover_from_directory(path: Path, config: Config) -> list[Path]:
    discovered: list[Path] = []
    for root, dirs, file_names in os.walk(path, followlinks=False):
        dirs[:] = [
            name
            for name in dirs
            if name not in DEFAULT_EXCLUDED_DIRS
            and not Path(root, name).is_symlink()
        ]

        for file_name in file_names:
            if not file_name.endswith(".py"):
                continue

            candidate = Path(root, file_name)
            if candidate.is_symlink():
                continue
            if _is_user_excluded(candidate, config):
                continue
            discovered.append(candidate.resolve())
    return discovered


def _is_user_excluded(candidate: Path, config: Config) -> bool:
    if not config.exclude:
        return False

    rel_path = Path(
        os.path.relpath(candidate, start=config.base_dir)
    ).as_posix()
    parts = tuple(part for part in rel_path.split("/") if part)
    return any(_match_pattern(parts, pattern) for pattern in config.exclude)


def _match_pattern(path_parts: tuple[str, ...], pattern: str) -> bool:
    pattern_parts = tuple(part for part in pattern.split("/") if part)
    return _match_segments(path_parts, pattern_parts)


def _match_segments(
    path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]
) -> bool:
    if not pattern_parts:
        return not path_parts

    head = pattern_parts[0]
    tail = pattern_parts[1:]

    if head == "**":
        for index in range(len(path_parts) + 1):
            if _match_segments(path_parts[index:], tail):
                return True
        return False

    if not path_parts:
        return False

    if not fnmatch.fnmatch(path_parts[0], head):
        return False

    return _match_segments(path_parts[1:], tail)

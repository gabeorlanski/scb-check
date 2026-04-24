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


class PathError(ValueError):  # scbc ignore[empty-exception-subclass]
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
            candidate = Path(root, file_name)
            if (
                not file_name.endswith(".py")
                or candidate.is_symlink()
                or _is_user_excluded(candidate, config)
            ):
                continue
            discovered.append(candidate.resolve())
    return discovered


def _is_user_excluded(candidate: Path, config: Config) -> bool:
    rel_path = Path(
        os.path.relpath(candidate, start=config.base_dir)
    ).as_posix()
    parts = tuple(part for part in rel_path.split("/") if part)
    return any(
        _match_pattern(parts, pattern) for pattern in config.exclude
    ) if config.exclude else False


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
        return any(
            _match_segments(path_parts[index:], tail)
            for index in range(len(path_parts) + 1)
        )

    return (
        path_parts != ()
        and fnmatch.fnmatch(path_parts[0], head)
        and _match_segments(path_parts[1:], tail)
    )

"""Discover supported source files while applying configured excludes."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from scb_check.config import Config
from scb_check.tree_walking.dispatch import SUPPORTED_SOURCE_SUFFIXES

_PYTHON_SUFFIXES = frozenset({".py"})

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


@dataclass(frozen=True, slots=True)
class _GitIgnoreRule:
    base_dir: Path
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool


def walk_source_files(
    path: Path,
    config: Config,
    *,
    include_ignored: bool = False,
    python_only: bool = False,
) -> Iterator[Path]:
    """Yield supported source files after applying discovery excludes.

    When `python_only` is set, only `.py` files are yielded and single-file
    inputs with another suffix raise ``ValueError("not a Python file: ...")``.
    """
    suffixes = _PYTHON_SUFFIXES if python_only else SUPPORTED_SOURCE_SUFFIXES
    file_kind = "Python" if python_only else "supported source"
    yield from _walk_supported_files(
        path,
        config,
        include_ignored=include_ignored,
        suffixes=suffixes,
        file_kind=file_kind,
    )


def walk_python_files(
    path: Path,
    config: Config,
    *,
    include_ignored: bool = False,
) -> Iterator[Path]:
    """Yield Python files under `path` after applying discovery excludes."""
    yield from walk_source_files(
        path, config, include_ignored=include_ignored, python_only=True,
    )


def _walk_supported_files(
    path: Path,
    config: Config,
    *,
    include_ignored: bool,
    suffixes: frozenset[str],
    file_kind: str,
) -> Iterator[Path]:
    if not path.exists():
        raise FileNotFoundError(f"path does not exist: {path}")

    if path.is_file():
        if path.suffix.lower() not in suffixes:
            raise ValueError(f"not a {file_kind} file: {path}")
        yield path.resolve()
        return

    root = path.resolve()
    gitignore_rules = () if include_ignored else _ancestor_gitignore_rules(root, config)
    yield from _walk_directory(
        root,
        config,
        include_ignored=include_ignored,
        gitignore_rules=gitignore_rules,
        suffixes=suffixes,
    )


def _walk_directory(
    root: Path,
    config: Config,
    *,
    include_ignored: bool,
    gitignore_rules: tuple[_GitIgnoreRule, ...],
    suffixes: frozenset[str],
) -> Iterator[Path]:
    active_gitignore_rules = gitignore_rules
    if not include_ignored:
        active_gitignore_rules = (*gitignore_rules, *_read_gitignore(root))

    for child in root.iterdir():
        yield from _walk_child(
            child,
            config,
            include_ignored=include_ignored,
            gitignore_rules=active_gitignore_rules,
            suffixes=suffixes,
        )


def _walk_child(
    child: Path,
    config: Config,
    *,
    include_ignored: bool,
    gitignore_rules: tuple[_GitIgnoreRule, ...],
    suffixes: frozenset[str],
) -> Iterator[Path]:
    if child.is_symlink():
        return

    if child.is_dir():
        if _is_discoverable_directory(child, gitignore_rules):
            yield from _walk_directory(
                child,
                config,
                include_ignored=include_ignored,
                gitignore_rules=gitignore_rules,
                suffixes=suffixes,
            )
        return

    if _is_discoverable_source_file(
        child,
        config,
        include_ignored=include_ignored,
        gitignore_rules=gitignore_rules,
        suffixes=suffixes,
    ):
        yield child.resolve()


def _is_discoverable_directory(
    path: Path,
    gitignore_rules: tuple[_GitIgnoreRule, ...],
) -> bool:
    return path.name not in DEFAULT_EXCLUDED_DIRS and not _is_gitignored(
        path,
        is_dir=True,
        rules=gitignore_rules,
    )


def _is_discoverable_source_file(
    path: Path,
    config: Config,
    *,
    include_ignored: bool,
    gitignore_rules: tuple[_GitIgnoreRule, ...],
    suffixes: frozenset[str],
) -> bool:
    return (
        path.suffix.lower() in suffixes
        and not _is_user_excluded(path, config)
        and (
            include_ignored
            or not _is_gitignored(path, is_dir=False, rules=gitignore_rules)
        )
    )


def _ancestor_gitignore_rules(root: Path, config: Config) -> tuple[_GitIgnoreRule, ...]:
    base_dir = _gitignore_base_dir(root, config.base_dir)
    return tuple(
        rule
        for directory in _ancestor_directories(base_dir, root)
        for rule in _read_gitignore(directory)
    )


def _gitignore_base_dir(root: Path, config_base_dir: Path) -> Path:
    for current in (root, *root.parents):
        if (current / ".git").exists():
            return current

    resolved_config_base = config_base_dir.resolve()
    try:
        root.relative_to(resolved_config_base)
    except ValueError:
        return root
    return resolved_config_base


def _ancestor_directories(base_dir: Path, root: Path) -> tuple[Path, ...]:
    if base_dir == root:
        return ()

    try:
        root.relative_to(base_dir)
    except ValueError:
        return ()

    directories: list[Path] = []
    current = root.parent
    while True:
        directories.append(current)
        if current == base_dir:
            return tuple(reversed(directories))
        current = current.parent


def _read_gitignore(directory: Path) -> tuple[_GitIgnoreRule, ...]:
    gitignore = directory / ".gitignore"
    if not gitignore.is_file():
        return ()

    return tuple(
        rule
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if (rule := _parse_gitignore_line(directory, line)) is not None
    )


def _parse_gitignore_line(base_dir: Path, line: str) -> _GitIgnoreRule | None:
    raw_pattern = line.strip()
    if not raw_pattern or raw_pattern.startswith("#"):
        return None

    negated = False
    if raw_pattern.startswith((r"\#", r"\!")):
        raw_pattern = raw_pattern[1:]
    elif raw_pattern.startswith("!"):
        negated = True
        raw_pattern = raw_pattern[1:].strip()

    normalized = raw_pattern.replace("\\", "/")
    directory_only = normalized.endswith("/")
    anchored = normalized.startswith("/")
    normalized = normalized.lstrip("/").rstrip("/")
    if not normalized:
        return None

    return _GitIgnoreRule(
        base_dir=base_dir.resolve(),
        pattern=normalized,
        negated=negated,
        directory_only=directory_only,
        anchored=anchored,
    )


def _is_gitignored(
    path: Path,
    *,
    is_dir: bool,
    rules: tuple[_GitIgnoreRule, ...],
) -> bool:
    ignored = False
    for rule in rules:
        if _matches_gitignore_rule(path, is_dir=is_dir, rule=rule):
            ignored = not rule.negated
    return ignored


def _matches_gitignore_rule(path: Path, *, is_dir: bool, rule: _GitIgnoreRule) -> bool:
    path_parts = _gitignore_relative_parts(path, rule)
    pattern_parts = _path_parts(rule.pattern)
    if path_parts is None or not pattern_parts:
        return False

    if _is_basename_gitignore_rule(rule, pattern_parts):
        return _matches_basename_gitignore_rule(
            path_parts,
            pattern_parts[0],
            rule,
            is_dir=is_dir,
        )

    return _matches_gitignore_path_rule(
        path_parts,
        pattern_parts,
        rule,
        is_dir=is_dir,
    )


def _gitignore_relative_parts(path: Path, rule: _GitIgnoreRule) -> tuple[str, ...] | None:
    try:
        rel_path = path.resolve().relative_to(rule.base_dir).as_posix()
    except ValueError:
        return None
    return _path_parts(rel_path)


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split("/") if part)


def _is_basename_gitignore_rule(
    rule: _GitIgnoreRule,
    pattern_parts: tuple[str, ...],
) -> bool:
    return not rule.anchored and len(pattern_parts) == 1


def _matches_gitignore_path_rule(
    path_parts: tuple[str, ...],
    pattern_parts: tuple[str, ...],
    rule: _GitIgnoreRule,
    *,
    is_dir: bool,
) -> bool:
    return any(
        _match_segments(candidate_parts, pattern_parts)
        for candidate_parts in _gitignore_path_candidates(
            path_parts,
            is_dir=is_dir,
            rule=rule,
        )
    )


def _matches_basename_gitignore_rule(
    path_parts: tuple[str, ...],
    pattern: str,
    rule: _GitIgnoreRule,
    *,
    is_dir: bool,
) -> bool:
    if not rule.directory_only:
        return any(fnmatch.fnmatch(part, pattern) for part in path_parts)

    directory_parts = path_parts if is_dir else path_parts[:-1]
    return any(fnmatch.fnmatch(part, pattern) for part in directory_parts)


def _gitignore_path_candidates(
    path_parts: tuple[str, ...],
    *,
    is_dir: bool,
    rule: _GitIgnoreRule,
) -> tuple[tuple[str, ...], ...]:
    if not rule.directory_only:
        return (path_parts, *_directory_path_candidates(path_parts, is_dir=is_dir))
    return _directory_path_candidates(path_parts, is_dir=is_dir)


def _directory_path_candidates(
    path_parts: tuple[str, ...],
    *,
    is_dir: bool,
) -> tuple[tuple[str, ...], ...]:
    last_index = len(path_parts) if is_dir else len(path_parts) - 1
    return tuple(path_parts[:index] for index in range(1, last_index + 1))


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

"""Load and validate `scb-check` configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration loaded from TOML or defaults."""

    exclude: tuple[str, ...]
    base_dir: Path
    context_lines: int = 1


class ConfigError(ValueError):  # scbc ignore[empty-exception-subclass]
    """Raised when configuration discovery or validation fails."""


def load_config(override_path: Path | None, cwd: Path) -> Config:
    """Load configuration from `override_path`, discovery, or defaults."""
    if override_path is not None:
        if not override_path.exists():
            raise ConfigError(f"config path does not exist: {override_path}")
        return _parse_config_file(override_path)

    path = _discover_config(cwd)
    if path is None:
        return Config(exclude=(), base_dir=cwd, context_lines=1)
    return _parse_config_file(path)


def _discover_config(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        scb_check_file = current / "scb-check.toml"
        if scb_check_file.is_file():
            return scb_check_file

        pyproject = current / "pyproject.toml"
        if pyproject.is_file() and _has_config(pyproject):
            return pyproject

        if (current / ".git").is_dir() or current.parent == current:
            return None
        current = current.parent


def _has_config(path: Path) -> bool:
    data = _load_toml(path)
    tool = data.get("tool")
    raw_ty = tool.get("ty") if isinstance(tool, dict) else None
    return isinstance(tool, dict) and (
        isinstance(tool.get("scb-check"), dict)
        or isinstance(tool.get("ruff"), dict)
        or (isinstance(raw_ty, dict) and isinstance(raw_ty.get("src"), dict))
    )


def _parse_config_file(path: Path) -> Config:
    # scbc boundary: normalize user config from TOML.
    payload = _load_toml(path)

    if path.name != "pyproject.toml":
        exclude, context_lines = _scb_table(path, payload)
        return Config(
            exclude=exclude,
            base_dir=path.parent,
            context_lines=context_lines,
        )

    exclude: tuple[str, ...] = ()
    context_lines = 1

    tool = payload.get("tool")
    if isinstance(tool, dict):
        raw_scb_check = tool.get("scb-check")
        if raw_scb_check is not None:
            if not isinstance(raw_scb_check, dict):
                raise ConfigError(f"{path}: [tool.scb-check] must be a table")
            exclude, context_lines = _scb_table(path, raw_scb_check)

        exclude = tuple(
            dict.fromkeys((*exclude, *_tool_excludes(tool))),
        )

    return Config(
        exclude=exclude,
        base_dir=path.parent,
        context_lines=context_lines,
    )


def _tool_excludes(tool: dict[str, Any]) -> tuple[str, ...]:
    # scbc boundary: imports exclusion config from other tools.
    patterns: list[str] = []

    raw_ruff = tool.get("ruff")
    if isinstance(raw_ruff, dict):
        patterns.extend(_strings(raw_ruff.get("exclude")))
        patterns.extend(_strings(raw_ruff.get("extend-exclude")))

    raw_ty = tool.get("ty")
    if isinstance(raw_ty, dict):
        raw_ty_src = raw_ty.get("src")
        if isinstance(raw_ty_src, dict):
            patterns.extend(_strings(raw_ty_src.get("exclude")))

    return _norm_patterns(tuple(patterns))


def _strings(
    value: object,  # scbc ignore[object-type-annotation]
) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return tuple(str(entry) for entry in value)
    return ()


def _norm_patterns(patterns: tuple[str, ...]) -> tuple[str, ...]:
    normalized_patterns = tuple(
        normalized
        for raw_pattern in patterns
        for normalized in _norm_pattern(raw_pattern)
    )
    return tuple(dict.fromkeys(normalized_patterns))


def _norm_pattern(raw_pattern: str) -> tuple[str, ...]:
    normalized = raw_pattern.strip().replace("\\", "/")
    normalized = normalized.removeprefix("./")
    normalized = normalized.lstrip("/")
    if not normalized:
        return ()

    if normalized.endswith("/"):
        return (f"{normalized.rstrip('/')}/**",)

    if any(char in normalized for char in "*?[]") or normalized.endswith(".py"):
        return (normalized,)

    return (normalized, f"{normalized}/**")


def _scb_table(
    path: Path,
    table: dict[str, Any],
) -> tuple[tuple[str, ...], int]:
    # scbc boundary: validates scb-check TOML fields.
    unknown = set(table) - {"exclude", "context"}
    if unknown:
        raise ConfigError(f"{path}: unknown key: {min(unknown)}")

    exclude = table.get("exclude", ())
    if not isinstance(exclude, (list, tuple)):
        raise ConfigError(f"{path}: exclude must be a list")
    if not all(isinstance(entry, str) for entry in exclude):
        raise ConfigError(f"{path}: exclude must be a list of strings")

    context = table.get("context", 1)
    if not isinstance(context, int):
        raise ConfigError(f"{path}: context must be an integer")
    if context < 0:
        raise ConfigError(f"{path}: context must be >= 0")

    return tuple(exclude), context


def _load_toml(path: Path) -> dict[str, Any]:
    # scbc boundary: validates file IO and TOML syntax.
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}: failed to read config") from exc

    try:
        return tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

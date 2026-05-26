"""Load and validate `scb-check` configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, cast

from scb_check.rules.settings import LowUseShortFunctionSettings


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration loaded from TOML or defaults."""

    exclude: tuple[str, ...]
    base_dir: Path
    context_lines: int = 1
    low_use_short_function: LowUseShortFunctionSettings = field(
        default_factory=LowUseShortFunctionSettings,
    )


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
        exclude, context_lines, low_use_short_function = _scb_table(path, payload)
        return Config(
            exclude=exclude,
            base_dir=path.parent,
            context_lines=context_lines,
            low_use_short_function=low_use_short_function,
        )

    exclude: tuple[str, ...] = ()
    context_lines = 1
    low_use_short_function = LowUseShortFunctionSettings()

    tool = payload.get("tool")
    if isinstance(tool, dict):
        raw_scb_check = tool.get("scb-check")
        if raw_scb_check is not None:
            if not isinstance(raw_scb_check, dict):
                raise ConfigError(f"{path}: [tool.scb-check] must be a table")
            exclude, context_lines, low_use_short_function = _scb_table(
                path,
                raw_scb_check,
            )

        exclude = tuple(
            dict.fromkeys((*exclude, *_tool_excludes(tool))),
        )

    return Config(
        exclude=exclude,
        base_dir=path.parent,
        context_lines=context_lines,
        low_use_short_function=low_use_short_function,
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
) -> tuple[tuple[str, ...], int, LowUseShortFunctionSettings]:
    # scbc boundary: validates scb-check TOML fields.
    unknown = set(table) - {"exclude", "context", "low-use-short-function"}
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

    low_use_short_function = _low_use_short_function_settings(
        path,
        table.get("low-use-short-function", {}),
    )

    return tuple(exclude), context, low_use_short_function


def _low_use_short_function_settings(
    path: Path,
    value: object,
) -> LowUseShortFunctionSettings:
    if value == {}:
        return LowUseShortFunctionSettings()
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: low-use-short-function must be a table")
    settings = cast("dict[str, Any]", value)
    unknown = set(settings) - {
        "enabled",
        "max-call-sites",
        "max-function-sloc",
        "max-inline-caller-sloc",
        "max-inline-caller-complexity",
        "max-inline-caller-cognitive-complexity",
        "max-inline-call-nesting",
    }
    if unknown:
        raise ConfigError(
            f"{path}: unknown low-use-short-function key: {min(unknown)}",
        )
    return LowUseShortFunctionSettings(
        enabled=_enabled_setting(path, settings),
        max_call_sites=_min_int_setting(
            path,
            settings,
            "max-call-sites",
            2,
            minimum=1,
        ),
        max_function_sloc=_min_int_setting(
            path,
            settings,
            "max-function-sloc",
            5,
            minimum=1,
        ),
        max_inline_caller_sloc=_min_int_setting(
            path,
            settings,
            "max-inline-caller-sloc",
            50,
            minimum=1,
        ),
        max_inline_caller_complexity=_min_int_setting(
            path,
            settings,
            "max-inline-caller-complexity",
            10,
            minimum=1,
        ),
        max_inline_caller_cognitive_complexity=_min_int_setting(
            path,
            settings,
            "max-inline-caller-cognitive-complexity",
            10,
            minimum=0,
        ),
        max_inline_call_nesting=_min_int_setting(
            path,
            settings,
            "max-inline-call-nesting",
            3,
            minimum=0,
        ),
    )


def _enabled_setting(path: Path, table: dict[str, Any]) -> bool:
    value = table.get("enabled", False)
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: enabled must be a boolean")
    return value


def _min_int_setting(
    path: Path,
    table: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
) -> int:
    value = _int_setting(path, table, key, default)
    if value < minimum:
        raise ConfigError(f"{path}: {key} must be >= {minimum}")
    return value


def _int_setting(
    path: Path,
    table: dict[str, Any],
    key: str,
    default: int,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}: {key} must be an integer")
    return value


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

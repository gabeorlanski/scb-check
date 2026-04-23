from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Config:
    exclude: tuple[str, ...]
    base_dir: Path
    context_lines: int = 1


class ConfigError(ValueError):
    pass


def load_config(override_path: Path | None, cwd: Path) -> Config:
    path = _resolve_config_path(override_path, cwd)
    if path is None:
        return Config(exclude=(), base_dir=cwd, context_lines=1)
    return _parse_config_file(path)


def _resolve_config_path(override_path: Path | None, cwd: Path) -> Path | None:
    if override_path is not None:
        if not override_path.exists():
            raise ConfigError(f"config path does not exist: {override_path}")
        return override_path
    return _discover_config(cwd)


def _discover_config(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        scb_check_file = current / "scb-check.toml"
        if scb_check_file.is_file():
            return scb_check_file

        pyproject = current / "pyproject.toml"
        if pyproject.is_file() and _pyproject_has_supported_config(pyproject):
            return pyproject

        if (current / ".git").is_dir() or current.parent == current:
            return None
        current = current.parent


def _pyproject_has_supported_config(path: Path) -> bool:
    data = _load_toml(path)
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False
    if isinstance(tool.get("scb-check"), dict):
        return True
    if isinstance(tool.get("ruff"), dict):
        return True

    raw_ty = tool.get("ty")
    if not isinstance(raw_ty, dict):
        return False
    return isinstance(raw_ty.get("src"), dict)


def _parse_config_file(path: Path) -> Config:
    payload = _load_toml(path)

    if path.name != "pyproject.toml":
        exclude, context_lines = _validate_scb_check_table(path, payload)
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
            exclude, context_lines = _validate_scb_check_table(
                path, raw_scb_check
            )

        tool_excludes = _extract_external_tool_excludes(tool)
        exclude = _merge_excludes(exclude, tool_excludes)

    return Config(
        exclude=exclude,
        base_dir=path.parent,
        context_lines=context_lines,
    )


def _extract_external_tool_excludes(tool: dict[str, Any]) -> tuple[str, ...]:
    patterns: list[str] = []

    raw_ruff = tool.get("ruff")
    if isinstance(raw_ruff, dict):
        patterns.extend(_read_string_list(raw_ruff.get("exclude")))
        patterns.extend(_read_string_list(raw_ruff.get("extend-exclude")))

    raw_ty = tool.get("ty")
    if isinstance(raw_ty, dict):
        raw_ty_src = raw_ty.get("src")
        if isinstance(raw_ty_src, dict):
            patterns.extend(_read_string_list(raw_ty_src.get("exclude")))

    return _normalize_tool_patterns(tuple(patterns))


def _read_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    if not all(isinstance(entry, str) for entry in value):
        return ()
    return tuple(value)


def _normalize_tool_patterns(patterns: tuple[str, ...]) -> tuple[str, ...]:
    normalized_patterns: list[str] = []

    for raw_pattern in patterns:
        normalized = raw_pattern.strip().replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = normalized.lstrip("/")
        if not normalized:
            continue

        if normalized.endswith("/"):
            normalized_patterns.append(f"{normalized.rstrip('/')}/**")
            continue

        normalized_patterns.append(normalized)
        if _is_glob_pattern(normalized) or normalized.endswith(".py"):
            continue
        normalized_patterns.append(f"{normalized}/**")

    return tuple(dict.fromkeys(normalized_patterns))


def _is_glob_pattern(pattern: str) -> bool:
    return any(char in pattern for char in "*?[]")


def _merge_excludes(
    primary: tuple[str, ...],
    secondary: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*primary, *secondary)))


def _validate_scb_check_table(
    path: Path, table: dict[str, Any]
) -> tuple[tuple[str, ...], int]:
    allowed = {"exclude", "context"}
    for key in table:
        if key not in allowed:
            raise ConfigError(f"{path}: unknown key: {key}")

    exclude = table.get("exclude", [])
    if not isinstance(exclude, list):
        raise ConfigError(f"{path}: exclude must be a list")
    if not all(isinstance(entry, str) for entry in exclude):
        raise ConfigError(f"{path}: exclude must be a list of strings")

    context = table.get("context", 1)
    if not isinstance(context, int) or isinstance(context, bool):
        raise ConfigError(f"{path}: context must be an integer")
    if context < 0:
        raise ConfigError(f"{path}: context must be >= 0")

    return tuple(exclude), context


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}: failed to read config") from exc

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: config root must be a table")
    return data

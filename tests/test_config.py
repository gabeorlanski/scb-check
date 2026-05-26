from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.config import ConfigError
from scb_check.config import load_config


def test_prefers_scb_toml(tmp_path: Path) -> None:
    """scb-check.toml takes precedence over pyproject configuration."""
    root = tmp_path / "repo"
    nested = root / "pkg" / "app"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "scb-check.toml").write_text(
        'exclude = ["generated/**", "tests/fixtures/*"]\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[tool.scb-check]\nexclude = ["ignored/*"]\n',
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert config.exclude == ("generated/**", "tests/fixtures/*")
    assert config.base_dir == root


def test_reads_pyproject_section(tmp_path: Path) -> None:
    """Pyproject tool.scb-check settings are discovered from repo roots."""
    root = tmp_path / "repo"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname='x'\n[tool.scb-check]\nexclude=[\"build/**\"]\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert config.exclude == ("build/**",)
    assert config.base_dir == root


def test_imports_tool_excludes(
    tmp_path: Path,
) -> None:
    """Ruff and ty excludes are imported when no scb-check section exists."""
    root = tmp_path / "repo"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.ruff]",
                'exclude = ["vendor/"]',
                "",
                "[tool.ty.src]",
                'exclude = ["tests/fixtures/"]',
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert "vendor/**" in config.exclude
    assert "tests/fixtures/**" in config.exclude
    assert config.context_lines == 1


def test_merges_tool_excludes(
    tmp_path: Path,
) -> None:
    """scb-check, Ruff, and ty exclude patterns are merged."""
    root = tmp_path / "repo"
    nested = root / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.scb-check]",
                'exclude = ["custom/**"]',
                "context = 2",
                "",
                "[tool.ruff]",
                'exclude = ["vendor/", ".venv"]',
                'extend-exclude = ["generated/"]',
                "",
                "[tool.ty.src]",
                'exclude = ["tests/fixtures/"]',
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert config.context_lines == 2
    assert "custom/**" in config.exclude
    assert "vendor/**" in config.exclude
    assert ".venv/**" in config.exclude
    assert "generated/**" in config.exclude
    assert "tests/fixtures/**" in config.exclude


def test_ignores_bad_tool_excludes_with_scb(
    tmp_path: Path,
) -> None:
    """Invalid external tool exclude shapes do not override scb-check settings."""
    root = tmp_path / "repo"
    nested = root / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.scb-check]",
                'exclude = ["custom/**"]',
                "context = 2",
                "",
                "[tool.ruff]",
                'exclude = "vendor/"',
                'extend-exclude = ["generated/", 3]',
                "",
                "[tool.ty]",
                'src = "not-a-table"',
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert config.context_lines == 2
    assert config.exclude == ("custom/**",)


def test_ignores_bad_tool_excludes_explicit(
    tmp_path: Path,
) -> None:
    """Explicit pyproject configs ignore invalid external tool exclude shapes."""
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(
        "\n".join(
            [
                "[tool.ruff]",
                'exclude = "vendor/"',
                "",
                "[tool.ty]",
                'src = "not-a-table"',
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_file, tmp_path)

    assert config.exclude == ()
    assert config.context_lines == 1
    assert config.base_dir == tmp_path


def test_reads_low_use_short_function_settings(tmp_path: Path) -> None:
    """Inline-safety budgets for low-use helpers are read from config."""
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text(
        "\n".join(
            [
                "[low-use-short-function]",
                "enabled = false",
                "max-call-sites = 1",
                "max-function-sloc = 4",
                "max-inline-caller-sloc = 20",
                "max-inline-caller-complexity = 8",
                "max-inline-caller-cognitive-complexity = 7",
                "max-inline-call-nesting = 2",
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_file, tmp_path)

    assert not config.low_use_short_function.enabled
    assert config.low_use_short_function.max_call_sites == 1
    assert config.low_use_short_function.max_function_sloc == 4
    assert config.low_use_short_function.max_inline_caller_sloc == 20
    assert config.low_use_short_function.max_inline_caller_complexity == 8
    assert config.low_use_short_function.max_inline_caller_cognitive_complexity == 7
    assert config.low_use_short_function.max_inline_call_nesting == 2


def test_rejects_invalid_low_use_short_function_settings(tmp_path: Path) -> None:
    """Invalid low-use helper budgets raise ConfigError."""
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text(
        "[low-use-short-function]\nmax-call-sites = 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="max-call-sites must be >= 1"):
        load_config(config_file, tmp_path)


def test_rejects_unknown_explicit_keys(tmp_path: Path) -> None:
    """Unknown keys in an explicit config raise ConfigError."""
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("exclude = []\nextra = true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="unknown key: extra"):
        load_config(config_file, tmp_path)


def test_rejects_unknown_discovered_keys(
    tmp_path: Path,
) -> None:
    """Unknown discovered scb-check keys raise ConfigError."""
    root = tmp_path / "repo"
    nested = root / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.scb-check]",
                "extra = true",
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown key: extra"):
        load_config(None, nested)


def test_rejects_non_list_exclude(tmp_path: Path) -> None:
    """Non-list exclude values raise ConfigError."""
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text('exclude = "tests/**"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="exclude must be a list"):
        load_config(config_file, tmp_path)


def test_rejects_missing_config(tmp_path: Path) -> None:
    """Missing explicit config paths raise ConfigError."""
    config_file = tmp_path / "missing.toml"

    with pytest.raises(ConfigError, match="config path does not exist"):
        load_config(config_file, tmp_path)

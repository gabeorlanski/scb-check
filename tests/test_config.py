from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.config import ConfigError
from scb_check.config import load_config


def test_load_config_prefers_scb_check_toml(tmp_path: Path) -> None:
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


def test_load_config_reads_tool_table_from_pyproject(tmp_path: Path) -> None:
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


def test_load_config_discovers_pyproject_with_ruff_and_ty_only(
    tmp_path: Path,
) -> None:
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert "vendor/**" in config.exclude
    assert "tests/fixtures/**" in config.exclude
    assert config.context_lines == 1


def test_load_config_merges_ruff_ty_excludes_and_context(
    tmp_path: Path,
) -> None:
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
            ]
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


def test_load_config_ignores_malformed_external_tool_tables(
    tmp_path: Path,
) -> None:
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(None, nested)

    assert config.context_lines == 2
    assert config.exclude == ("custom/**",)


def test_load_config_with_malformed_external_override_uses_defaults(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(
        "\n".join(
            [
                "[tool.ruff]",
                'exclude = "vendor/"',
                "",
                "[tool.ty]",
                'src = "not-a-table"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_file, tmp_path)

    assert config.exclude == ()
    assert config.context_lines == 1
    assert config.base_dir == tmp_path


def test_load_config_raises_for_unknown_key(tmp_path: Path) -> None:
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("exclude = []\nextra = true\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="unknown key: extra"):
        load_config(config_file, tmp_path)


def test_load_config_raises_for_unknown_key_in_tool_scb_check(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    nested = root / "pkg"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.scb-check]",
                "extra = true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown key: extra"):
        load_config(None, nested)


def test_load_config_raises_for_wrong_exclude_type(tmp_path: Path) -> None:
    config_file = tmp_path / "scb-check.toml"
    config_file.write_text('exclude = "tests/**"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="exclude must be a list"):
        load_config(config_file, tmp_path)


def test_missing_override_path_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "missing.toml"

    with pytest.raises(ConfigError, match="config path does not exist"):
        load_config(config_file, tmp_path)

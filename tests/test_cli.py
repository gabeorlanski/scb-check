from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Never

import click
import yaml
from typer.testing import CliRunner

from scb_check.cli import main
from scb_check.config import Config
from scb_check.models import AstGrepHit
from scb_check.models import Flags
from scb_check.pipeline import AnalysisResult
from scb_check.pipeline import IgnoreDirectiveError

if TYPE_CHECKING:
    import pytest


def _fake_chained_dict_get_hit(
    files: tuple[Path, ...],
    _rules_path: Path,
) -> tuple[AstGrepHit, ...]:
    target = next(file for file in files if file.name == "module_c.py")
    return (
        AstGrepHit(
            file=target,
            line=2,
            end_line=2,
            col=12,
            end_col=48,
            rule_id="chained-dict-get",
            matched_text='cfg.get("a", {}).get("b", {}).get("c")',
        ),
    )


def test_check_report_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The check --report option emits a JSON summary."""
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda _files, _rules_path: (),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "check",
            "--config",
            str(config_override),
            "--report",
            str(corpus),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload.keys() == {
        "verbosity",
        "erosion",
        "cog_erosion",
        "files_scanned",
        "total_loc",
        "verbosity_flagged_loc",
        "clone_loc",
        "ast_grep_flagged_loc",
        "total_functions",
        "high_cc_functions",
        "high_cog_functions",
        "total_mass",
        "high_cc_mass",
        "total_cog_mass",
        "high_cog_mass",
    }


def test_check_human_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The default check command emits human-readable findings."""
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        _fake_chained_dict_get_hit,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--config", str(config_override), str(corpus)],
    )

    assert result.exit_code == 0
    assert "duplicate-structure" in result.stdout
    assert "warning[chained-dict-get]" in result.stdout
    assert (
        "erosion: function `complex_route` exceeds complexity threshold"
        in result.stdout
    )
    assert (
        "cog_erosion: function `complex_route` exceeds cognitive complexity threshold"
        in result.stdout
    )


def test_check_duplicates_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The structural duplicate mode suppresses other finding types."""
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        _fake_chained_dict_get_hit,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "check",
            "--config",
            str(config_override),
            "--duplicates-only",
            str(corpus),
        ],
    )

    assert result.exit_code == 0
    assert "duplicate-structure:" in result.stdout
    assert "warning[chained-dict-get]" not in result.stdout
    assert "erosion:" not in result.stdout
    assert "cog_erosion:" not in result.stdout


def test_check_rejects_report_with_duplicates_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Report and duplicate-only output modes are mutually exclusive."""
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda _files, _rules_path: (),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--report", "--duplicates-only", str(source)],
    )

    output = click.unstyle(result.output)
    assert result.exit_code == 2
    assert "--report" in output
    assert "--duplicates-only" in output
    assert "cannot be used together" in output


def test_check_missing_path() -> None:
    """Missing input paths are rejected with a usage error."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "does/not/exist.py"],
    )

    assert result.exit_code == 2
    assert "path does not exist" in result.output


def test_check_non_python_file(tmp_path: Path) -> None:
    """Non-Python file inputs are rejected."""
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source)])

    assert result.exit_code == 2
    assert "not a Python file" in result.output


def test_check_missing_config(tmp_path: Path) -> None:
    """Missing explicit config paths are rejected."""
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")
    config_path = tmp_path / "missing.toml"

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--config", str(config_path), str(source)],
    )

    assert result.exit_code == 2
    assert f"config path does not exist: {config_path}" in result.output


def test_check_report_skips_bad_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Report mode skips files that fail parsing and counts valid files."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    (source_dir / "ok.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8",
    )
    (source_dir / "broken.py").write_text(
        "def bad(:\n    return 0\n", encoding="utf-8",
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda _files, _rules_path: (),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--report", str(source_dir)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1


def test_check_empty_directory(tmp_path: Path) -> None:
    """Directories without Python files are rejected."""
    source_dir = tmp_path / "empty"
    source_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 2
    assert "no Python files found" in result.output


def test_rule_shows_yaml() -> None:
    """Known rule IDs print their bundled rule YAML."""
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "chained-dict-get"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["id"] == "chained-dict-get"


def test_rule_unknown_id() -> None:
    """Unknown rule IDs are rejected."""
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "does-not-exist"])

    assert result.exit_code == 2
    assert "rule not found: does-not-exist" in result.output


def test_check_passes_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Config context is passed to rendering."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("context = 3\n", encoding="utf-8")

    def fake_analyze(
        path: Path,
        config: Config,
        *,
        include_all: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is False
        return AnalysisResult(
            flags=Flags.from_parts(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    captured: dict[str, int] = {}

    def fake_render(
        flags: Flags,
        source_lines_by_file: dict[Path, tuple[str, ...]],
        *,
        context_lines: int,
    ) -> str:
        del flags, source_lines_by_file
        captured["context_lines"] = context_lines
        return ""

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)
    monkeypatch.setattr("scb_check.commands.check.render_flags", fake_render)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--config", str(config_file), "-vv", str(source_dir)],
    )

    assert result.exit_code == 0
    assert captured["context_lines"] == 3


def test_check_verbosity_sets_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The --verbosity option sets logging verbosity."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("context = 1\n", encoding="utf-8")

    def fake_analyze(
        path: Path,
        config: Config,
        *,
        include_all: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is False
        return AnalysisResult(
            flags=Flags.from_parts(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    captured: dict[str, int] = {}

    def fake_configure_logging(verbosity: int) -> None:
        captured["verbosity"] = verbosity

    def fake_render(
        flags: Flags,
        source_lines_by_file: dict[Path, tuple[str, ...]],
        *,
        context_lines: int,
    ) -> str:
        del flags, source_lines_by_file, context_lines
        return ""

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)
    monkeypatch.setattr(
        "scb_check.commands.check.configure_logging",
        fake_configure_logging,
    )
    monkeypatch.setattr("scb_check.commands.check.render_flags", fake_render)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "check",
            "--config",
            str(config_file),
            "--verbosity",
            str(source_dir),
        ],
    )

    assert result.exit_code == 0
    assert captured["verbosity"] == 1


def test_check_include_all(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The --include-all flag is passed to analysis."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    def fake_analyze(
        path: Path,
        config: Config,
        *,
        include_all: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is True
        return AnalysisResult(
            flags=Flags.from_parts(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", "--include-all", str(source_dir)])

    assert result.exit_code == 0


def test_check_reports_ignore_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directive errors are reported as usage failures."""
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")

    def fake_analyze(
        path: Path,
        config: Config,
        *,
        include_all: bool = False,
    ) -> Never:
        del path, config, include_all
        raise IgnoreDirectiveError(
            "sample.py:12: scbc ignore requires at least one rule id",
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source)])

    assert result.exit_code == 2
    assert (
        "sample.py:12: scbc ignore requires at least one rule id"
        in result.output
    )

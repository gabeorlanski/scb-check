from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from scb_check.cli import main
from scb_check.models import AstGrepHit
from scb_check.models import Flags
from scb_check.pipeline import AnalysisResult
from scb_check.pipeline import IgnoreDirectiveError


def test_cli_report_mode_outputs_json(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
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
        "files_scanned",
        "total_loc",
        "verbosity_flagged_loc",
        "clone_loc",
        "ast_grep_flagged_loc",
        "total_functions",
        "high_cc_functions",
        "total_mass",
        "high_cc_mass",
    }


def test_cli_default_mode_emits_flag_text(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")

    def fake_ast_grep(files, rules_path):  # type: ignore[no-untyped-def]
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

    monkeypatch.setattr("scb_check.pipeline.run_sg", fake_ast_grep)

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


def test_cli_returns_exit_2_for_missing_path() -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "does/not/exist.py"],
    )

    assert result.exit_code == 2
    assert "path does not exist" in result.output


def test_cli_returns_exit_2_for_non_python_file(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source)])

    assert result.exit_code == 2
    assert f"not a Python file: {source}" in result.output


def test_cli_returns_exit_2_for_missing_config_path(tmp_path: Path) -> None:
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


def test_cli_skips_parse_failures_and_continues(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    (source_dir / "ok.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8"
    )
    (source_dir / "broken.py").write_text(
        "def bad(:\n    return 0\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--report", str(source_dir)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1


def test_cli_returns_exit_2_when_no_python_files_found(tmp_path: Path) -> None:
    source_dir = tmp_path / "empty"
    source_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 2
    assert "no Python files found" in result.output


def test_cli_rule_prints_requested_yaml_rule() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "chained-dict-get"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["id"] == "chained-dict-get"


def test_cli_rule_returns_exit_2_for_unknown_rule() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "does-not-exist"])

    assert result.exit_code == 2
    assert "rule not found: does-not-exist" in result.output


def test_cli_passes_context_and_verbosity_to_render(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("context = 3\n", encoding="utf-8")

    def fake_analyze(files):  # type: ignore[no-untyped-def]
        resolved = source_file.resolve()
        assert files == (resolved,)
        return AnalysisResult(
            flags=Flags.from_parts(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    captured: dict[str, int] = {}

    def fake_render(  # type: ignore[no-untyped-def]
        flags, source_lines_by_file, context_lines, verbosity
    ):
        del flags, source_lines_by_file
        captured["context_lines"] = context_lines
        captured["verbosity"] = verbosity
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
    assert captured["verbosity"] == 2


def test_cli_supports_long_verbosity_option(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    config_file = tmp_path / "scb-check.toml"
    config_file.write_text("context = 1\n", encoding="utf-8")

    def fake_analyze(files):  # type: ignore[no-untyped-def]
        resolved = source_file.resolve()
        assert files == (resolved,)
        return AnalysisResult(
            flags=Flags.from_parts(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    captured: dict[str, int] = {}

    def fake_render(  # type: ignore[no-untyped-def]
        flags, source_lines_by_file, context_lines, verbosity
    ):
        del flags, source_lines_by_file, context_lines
        captured["verbosity"] = verbosity
        return ""

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)
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


def test_cli_returns_exit_2_for_ignore_directive_error(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")

    def fake_analyze(files):  # type: ignore[no-untyped-def]
        del files
        raise IgnoreDirectiveError(
            "sample.py:12: scbc ignore requires at least one rule id"
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source)])

    assert result.exit_code == 2
    assert (
        "sample.py:12: scbc ignore requires at least one rule id"
        in result.output
    )

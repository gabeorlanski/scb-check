from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Never

import yaml
from typer.testing import CliRunner

from scb_check.cli import main
from scb_check.config import Config
from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.pipeline import AnalysisResult
from scb_check.pipeline import IgnoreDirectiveError

if TYPE_CHECKING:
    import pytest


_REPORT_KEYS = {
    "verbosity",
    "erosion",
    "cog_erosion",
    "files_scanned",
    "total_loc",
    "verbosity_flagged_loc",
    "clone_loc",
    "ast_grep_flagged_loc",
    "structural_rule_loc",
    "structural_rule_findings",
    "total_functions",
    "high_cc_functions",
    "high_cog_functions",
    "total_mass",
    "high_cc_mass",
    "total_cog_mass",
    "high_cog_mass",
    "syntax_tree_count",
    "syntax_node_count",
    "syntax_by_language",
}


def _fake_json_loads_read_hit(
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
            rule_id="json-loads-read",
            matched_text="json.loads(f.read())",
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

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload.keys() == _REPORT_KEYS


def test_check_output_format_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The check --output-format json option emits a JSON summary."""
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
            "--output-format",
            "json",
            str(corpus),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload.keys() == _REPORT_KEYS



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
        _fake_json_loads_read_hit,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--config", str(config_override), str(corpus)],
    )

    assert result.exit_code == 1
    assert "duplicate-structure" in result.stdout
    assert "warning[json-loads-read]" in result.stdout
    assert (
        "erosion: function `complex_route` exceeds complexity threshold"
        in result.stdout
    )
    assert (
        "cog_erosion: function `complex_route` exceeds cognitive complexity threshold"
        in result.stdout
    )


def test_check_disable_sg_shows_non_sg_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Disabling sg skips ast-grep while keeping structural and erosion findings."""
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    config_override = tmp_path / "scb-check.toml"
    config_override.write_text("", encoding="utf-8")

    def fail_run_sg(_files: tuple[Path, ...], _rules_path: Path) -> tuple[AstGrepHit, ...]:
        raise AssertionError("sg should not run")

    monkeypatch.setattr("scb_check.pipeline.run_sg", fail_run_sg)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "check",
            "--config",
            str(config_override),
            "--disable-sg",
            str(corpus),
        ],
    )

    assert result.exit_code == 1
    assert "duplicate-structure:" in result.stdout
    assert "trivial-wrapper[warning]" in result.stdout
    assert "warning[json-loads-read]" not in result.stdout
    assert "erosion:" in result.stdout
    assert "cog_erosion:" in result.stdout


def test_check_report_accepts_supported_non_python_file(tmp_path: Path) -> None:
    """JSON reports include supported non-Python files."""
    source = tmp_path / "sample.rs"
    source.write_text(
        "fn compute(value: i32) -> i32 {\n    value + 1\n}\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["check", "--report", "--disable-sg", str(source)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1
    assert payload["total_functions"] == 1


def test_check_report_counts_syntax_by_language(tmp_path: Path) -> None:
    """JSON reports count syntax trees and nodes by source language."""
    python_source = tmp_path / "sample.py"
    python_source.write_text("value = 1\n", encoding="utf-8")
    rust_source = tmp_path / "sample.rs"
    rust_source.write_text(
        "fn compute(value: i32) -> i32 {\n    value + 1\n}\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["check", "--report", "--disable-sg", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    syntax_by_language = payload["syntax_by_language"]
    assert set(syntax_by_language) == {"python", "rust"}
    assert syntax_by_language["python"]["tree_count"] == 1
    assert syntax_by_language["python"]["node_count"] > 0
    assert syntax_by_language["rust"]["tree_count"] == 1
    assert syntax_by_language["rust"]["node_count"] > 0
    assert payload["syntax_tree_count"] == 2
    assert payload["syntax_node_count"] == sum(
        summary["node_count"] for summary in syntax_by_language.values()
    )


def test_check_report_allows_disable_sg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """JSON reports can disable sg because it is an analysis option."""
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")

    def fail_run_sg(_files: tuple[Path, ...], _rules_path: Path) -> tuple[AstGrepHit, ...]:
        raise AssertionError("sg should not run")

    monkeypatch.setattr("scb_check.pipeline.run_sg", fail_run_sg)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--report", "--disable-sg", str(source)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ast_grep_flagged_loc"] == 0


def test_check_filters_duplicates_by_line_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """The duplicate line filter hides smaller duplicate groups."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "sample.py"
    source_file.write_text(
        "\n".join(
            [
                "def small_first(value):",
                "    current = value + 1",
                "    return current",
                "",
                "def small_second(value):",
                "    current = value + 2",
                "    return current",
                "",
                "def large_first(value):",
                "    current = value + 1",
                "    doubled = current * 2",
                "    tripled = doubled * 3",
                "    return tripled",
                "",
                "def large_second(value):",
                "    current = value + 2",
                "    doubled = current * 2",
                "    tripled = doubled * 3",
                "    return tripled",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    resolved = source_file.resolve()
    small_a = CloneBlock(
        file=resolved,
        start_line=1,
        end_line=3,
        group_hash="small",
        instance_count=2,
        other_instances=((resolved, 5),),
        first_lines=(
            "def small_first(value):",
            "    current = value + 1",
            "    return current",
        ),
    )
    small_b = CloneBlock(
        file=resolved,
        start_line=5,
        end_line=7,
        group_hash="small",
        instance_count=2,
        other_instances=((resolved, 1),),
        first_lines=(
            "def small_second(value):",
            "    current = value + 2",
            "    return current",
        ),
    )
    large_a = CloneBlock(
        file=resolved,
        start_line=9,
        end_line=13,
        group_hash="large",
        instance_count=2,
        other_instances=((resolved, 15),),
        first_lines=(
            "def large_first(value):",
            "    current = value + 1",
            "    doubled = current * 2",
        ),
    )
    large_b = CloneBlock(
        file=resolved,
        start_line=15,
        end_line=19,
        group_hash="large",
        instance_count=2,
        other_instances=((resolved, 9),),
        first_lines=(
            "def large_second(value):",
            "    current = value + 2",
            "    doubled = current * 2",
        ),
    )

    def fake_analyze(
        path: Path,
        _config: Config,
        *,
        include_all: bool = False,
        disable_sg: bool = False,
    ) -> AnalysisResult:
        assert path == source_dir
        assert not include_all
        assert not disable_sg
        return AnalysisResult(
            flags=make_flags(
                clones=[small_a, small_b, large_a, large_b],
                total_loc_by_file=[(resolved, 16)],
                clone_sloc_lines_by_file=[
                    (resolved, {1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19}),
                ],
            ),
            source_lines_by_file={
                resolved: tuple(source_file.read_text(encoding="utf-8").splitlines()),
            },
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "--min-duplicate-lines", "5", str(source_dir)],
    )

    assert result.exit_code == 1
    assert "def large_first" in result.stdout
    assert "def large_second" in result.stdout
    assert "def small_first" not in result.stdout
    assert "def small_second" not in result.stdout


def test_check_missing_path() -> None:
    """Missing input paths are rejected with a usage error."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["check", "does/not/exist.py"],
    )

    assert result.exit_code == 2
    assert "path does not exist" in result.output


def test_check_unsupported_source_file(tmp_path: Path) -> None:
    """Unsupported file inputs are rejected."""
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source)])

    assert result.exit_code == 2
    assert "not a supported source file" in result.output


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
    """Directories without supported source files are rejected."""
    source_dir = tmp_path / "empty"
    source_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 2
    assert "no supported source files found" in result.output


def test_rule_shows_yaml() -> None:
    """Known rule IDs print their bundled rule YAML."""
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "chained-dict-get"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["id"] == "chained-dict-get"


def test_rule_shows_structural_metadata() -> None:
    """Known structural rule IDs print registry metadata."""
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "trivial-wrapper"])

    assert result.exit_code == 0
    payload = yaml.safe_load(result.stdout)
    assert payload["id"] == "trivial-wrapper"
    assert payload["severity"] == "warning"
    assert payload["target"] == "symbol"


def test_rule_unknown_id() -> None:
    """Unknown rule IDs are rejected."""
    runner = CliRunner()

    result = runner.invoke(main, ["rule", "does-not-exist"])

    assert result.exit_code == 2
    assert "rule not found: does-not-exist" in result.output


def test_check_passes_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
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
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is False
        assert disable_sg is False
        return AnalysisResult(
            flags=make_flags(total_loc_by_file=[(resolved, 1)]),
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
    make_flags: Callable[..., Flags],
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
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is False
        assert disable_sg is False
        return AnalysisResult(
            flags=make_flags(total_loc_by_file=[(resolved, 1)]),
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
    make_flags: Callable[..., Flags],
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
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del config
        resolved = source_file.resolve()
        assert path == source_dir
        assert include_all is True
        assert disable_sg is False
        return AnalysisResult(
            flags=make_flags(total_loc_by_file=[(resolved, 1)]),
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
        disable_sg: bool = False,
    ) -> Never:
        del path, config, include_all, disable_sg
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


def test_check_exits_zero_when_no_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """A clean codebase exits zero."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")
    resolved = source_file.resolve()

    def fake_analyze(
        _path: Path,
        _config: Config,
        *,
        include_all: bool = False,
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del include_all, disable_sg
        return AnalysisResult(
            flags=make_flags(total_loc_by_file=[(resolved, 1)]),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 0


def test_check_exits_nonzero_when_clones_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """A clone finding causes a non-zero exit."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")
    resolved = source_file.resolve()
    clone = CloneBlock(
        file=resolved,
        start_line=1,
        end_line=1,
        group_hash="h",
        instance_count=2,
        other_instances=((resolved, 1),),
        first_lines=("x = 1",),
    )

    def fake_analyze(
        _path: Path,
        _config: Config,
        *,
        include_all: bool = False,
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del include_all, disable_sg
        return AnalysisResult(
            flags=make_flags(
                clones=[clone],
                total_loc_by_file=[(resolved, 1)],
                clone_sloc_lines_by_file=[(resolved, {1})],
            ),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 1


def test_check_exits_nonzero_when_ast_hits_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """An ast-grep finding causes a non-zero exit."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")
    resolved = source_file.resolve()
    hit = AstGrepHit(
        file=resolved,
        line=1,
        end_line=1,
        col=0,
        end_col=5,
        rule_id="r",
        matched_text="x = 1",
    )

    def fake_analyze(
        _path: Path,
        _config: Config,
        *,
        include_all: bool = False,
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del include_all, disable_sg
        return AnalysisResult(
            flags=make_flags(
                ast_grep_hits=[hit],
                total_loc_by_file=[(resolved, 1)],
            ),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", str(source_dir)])

    assert result.exit_code == 1


def test_check_json_report_exits_nonzero_when_findings_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """The JSON report path also exits non-zero when findings exist."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    source_file = source_dir / "ok.py"
    source_file.write_text("x = 1\n", encoding="utf-8")
    resolved = source_file.resolve()
    clone = CloneBlock(
        file=resolved,
        start_line=1,
        end_line=1,
        group_hash="h",
        instance_count=2,
        other_instances=((resolved, 1),),
        first_lines=("x = 1",),
    )

    def fake_analyze(
        _path: Path,
        _config: Config,
        *,
        include_all: bool = False,
        disable_sg: bool = False,
    ) -> AnalysisResult:
        del include_all, disable_sg
        return AnalysisResult(
            flags=make_flags(
                clones=[clone],
                total_loc_by_file=[(resolved, 1)],
                clone_sloc_lines_by_file=[(resolved, {1})],
            ),
            source_lines_by_file={resolved: ("x = 1",)},
        )

    monkeypatch.setattr("scb_check.commands.check.analyze", fake_analyze)

    runner = CliRunner()
    result = runner.invoke(main, ["check", "--report", str(source_dir)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload.keys() == _REPORT_KEYS

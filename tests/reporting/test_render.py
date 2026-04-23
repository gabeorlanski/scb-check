from __future__ import annotations

from pathlib import Path

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.models import FunctionSymbol
from scb_check.reporting.render import render_flags


def test_render_flags_outputs_expected_templates(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def resolve_config(args):",
                "    if args:",
                "        return args",
                "    return {}",
                'value = cfg.get("a", {}).get("b", {}).get("c")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    clone_a = CloneBlock(
        file=file_path,
        start_line=2,
        end_line=4,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 20),),
        first_lines=("    if args:", "        return args", "    return {}"),
    )
    clone_b = CloneBlock(
        file=file_path,
        start_line=20,
        end_line=22,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 2),),
        first_lines=("    if args:", "        return args", "    return {}"),
    )
    ast_hit = AstGrepHit(
        file=file_path,
        line=5,
        end_line=5,
        col=8,
        end_col=42,
        rule_id="chained-dict-get",
        matched_text='cfg.get("a", {}).get("b", {}).get("c")',
        message=(
            "`.get().get()` chain - extract helper or use "
            "`operator.itemgetter` / try-except KeyError"
        ),
    )
    high_cc = FunctionSymbol(
        file=file_path,
        name="resolve_config",
        start_line=1,
        end_line=4,
        complexity=18,
        sloc=32,
    )
    flags = Flags.from_parts(
        clones=[clone_a, clone_b],
        ast_grep_hits=[ast_hit],
        high_cc_functions=[high_cc],
        total_loc_by_file=[(file_path, 5)],
        all_functions=[high_cc],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4})],
        ast_grep_sloc_lines_by_file=[(file_path, {5})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output = render_flags(flags, source_lines)

    assert (
        "duplicate-structure: duplicated block (3 lines, 2 instances)" in output
    )
    assert "warning[chained-dict-get]: `.get().get()` chain" in output
    assert ":5:9" in output
    assert (
        "erosion: function `resolve_config` exceeds complexity threshold"
        in output
    )
    assert "2 │     if args:" in output
    assert '5 │ value = cfg.get("a", {}).get("b", {}).get("c")' in output
    assert "complexity: 18, sloc: 32 (threshold: complexity > 10)" in output


def test_render_flags_renders_separate_warning_blocks_with_code(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def get_cfg_value(cfg):",
                '    value = cfg.get("a", {}).get("b", {}).get("c")',
                "    return value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    chained = AstGrepHit(
        file=file_path,
        line=2,
        end_line=2,
        col=12,
        end_col=50,
        rule_id="chained-dict-get",
        matched_text='cfg.get("a", {}).get("b", {}).get("c")',
        message=(
            "`.get().get()` chain - extract helper or use "
            "`operator.itemgetter` / try-except KeyError"
        ),
    )
    empty_dict = AstGrepHit(
        file=file_path,
        line=2,
        end_line=2,
        col=12,
        end_col=35,
        rule_id="dict-get-empty-dict-default",
        matched_text='cfg.get("a", {}).get("b", {})',
        message=(
            "`d.get(k, {})` - builds a fresh dict each call; "
            "use `d.setdefault(k, {})` or `defaultdict(dict)`"
        ),
    )
    flags = Flags.from_parts(
        ast_grep_hits=[chained, empty_dict],
        total_loc_by_file=[(file_path, 3)],
        ast_grep_sloc_lines_by_file=[(file_path, {2})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output = render_flags(flags, source_lines, context_lines=1)

    assert output.count("warning[") == 2
    assert output.count("┌─") == 2
    assert "warning[chained-dict-get]: `.get().get()` chain" in output
    assert "warning[dict-get-empty-dict-default]: `d.get(k, {})`" in output
    assert ":2:13" in output
    assert '2 │     value = cfg.get("a", {}).get("b", {}).get("c")' in output
    assert "^" not in output


def test_render_flags_respects_zero_context(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def get_cfg_value(cfg):",
                '    value = cfg.get("a", {}).get("b", {}).get("c")',
                "    return value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ast_hit = AstGrepHit(
        file=file_path,
        line=2,
        end_line=2,
        col=12,
        end_col=50,
        rule_id="chained-dict-get",
        matched_text='cfg.get("a", {}).get("b", {}).get("c")',
        message="`.get().get()` chain - extract helper",
    )
    flags = Flags.from_parts(
        ast_grep_hits=[ast_hit],
        total_loc_by_file=[(file_path, 3)],
        ast_grep_sloc_lines_by_file=[(file_path, {2})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output_with_zero = render_flags(flags, source_lines, context_lines=0)
    output_with_three = render_flags(flags, source_lines, context_lines=3)

    assert output_with_zero == output_with_three
    assert ":2:13" in output_with_zero
    assert (
        '2 │     value = cfg.get("a", {}).get("b", {}).get("c")'
        in output_with_zero
    )
    assert "^" not in output_with_zero


def test_render_flags_verbosity_does_not_change_rendered_text(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def get_cfg_value(cfg):",
                '    value = cfg.get("a", {}).get("b", {}).get("c")',
                "    return value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ast_hit = AstGrepHit(
        file=file_path,
        line=2,
        end_line=2,
        col=12,
        end_col=50,
        rule_id="chained-dict-get",
        matched_text='cfg.get("a", {}).get("b", {}).get("c")',
        message="`.get().get()` chain - extract helper",
    )
    flags = Flags.from_parts(
        ast_grep_hits=[ast_hit],
        total_loc_by_file=[(file_path, 3)],
        ast_grep_sloc_lines_by_file=[(file_path, {2})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output_default = render_flags(flags, source_lines)
    output_verbose = render_flags(flags, source_lines, verbosity=1)
    output_debug = render_flags(flags, source_lines, verbosity=2)

    assert output_default == output_verbose
    assert output_default == output_debug
    assert (
        '2 │     value = cfg.get("a", {}).get("b", {}).get("c")'
        in output_default
    )
    assert "^" not in output_default


def test_render_flags_multiline_hit_renders_snippet_lines(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def build():",
                '    value = "\\n".join(',
                '        ["a", "b"]',
                "    )",
                "    return value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ast_hit = AstGrepHit(
        file=file_path,
        line=2,
        end_line=4,
        col=12,
        end_col=5,
        rule_id="join-list-literal",
        matched_text='"\\n".join(\n        ["a", "b"]\n    )',
        message=(
            "`''.join([...])` materializes a list first - "
            "pass the iterable directly"
        ),
    )
    flags = Flags.from_parts(
        ast_grep_hits=[ast_hit],
        total_loc_by_file=[(file_path, 5)],
        ast_grep_sloc_lines_by_file=[(file_path, {2, 3, 4})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output = render_flags(flags, source_lines, context_lines=1)

    assert "warning[join-list-literal]" in output
    assert ":2:13" in output
    assert '2 │     value = "\\n".join(' in output
    assert '3 │         ["a", "b"]' in output
    assert "4 │     )" in output
    assert "^" not in output


def test_render_clone_uses_source_lines_for_full_duplicate_block(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def wrapper():",
                "    value = 1",
                "    value += 2",
                "    value += 3",
                "    value += 4",
                "    return value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    clone = CloneBlock(
        file=file_path,
        start_line=2,
        end_line=6,
        group_hash="abc123",
        instance_count=1,
        other_instances=(),
        first_lines=("    value = 1", "    value += 2", "    value += 3"),
    )
    flags = Flags.from_parts(
        clones=[clone],
        total_loc_by_file=[(file_path, 6)],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4, 5, 6})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output = render_flags(flags, source_lines)

    assert "2 │     value = 1" in output
    assert "6 │     return value" in output


def test_render_flags_groups_clone_instances_into_single_entry(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def first():",
                "    if args:",
                "        return args",
                "    return {}",
                "",
                "def second():",
                "    if args:",
                "        return args",
                "    return {}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    clone_a = CloneBlock(
        file=file_path,
        start_line=2,
        end_line=4,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 7),),
        first_lines=("    if args:", "        return args", "    return {}"),
    )
    clone_b = CloneBlock(
        file=file_path,
        start_line=7,
        end_line=9,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 2),),
        first_lines=("    if args:", "        return args", "    return {}"),
    )
    flags = Flags.from_parts(
        clones=[clone_a, clone_b],
        total_loc_by_file=[(file_path, 9)],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4, 7, 8, 9})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines())
    }

    output = render_flags(flags, source_lines)

    assert output.count("duplicate-structure:") == 1
    assert output.count("┌─") == 2
    assert f"┌─ {file_path.as_posix()}:2" in output
    assert f"┌─ {file_path.as_posix()}:7" in output
    assert "other instances:" not in output
    assert "2 │     if args:" in output
    assert "7 │     if args:" in output


def test_render_flags_returns_empty_string_for_no_flags() -> None:
    flags = Flags()

    assert render_flags(flags, {}) == ""

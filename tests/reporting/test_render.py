from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import Flags
from scb_check.reporting.render import render_flags
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import Severity
from scb_check.tree_walking.models import SignatureIR
from scb_check.tree_walking.models import SourceSpan
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind


def test_renders_all_finding_types(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Rendered output includes clone, ast-grep, and erosion findings."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def resolve_config(args):",
                "    if args:",
                "        return args",
                "    return {}",
                'value = cfg.get("a", {}).get("b", {}).get("c")',
            ],
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
    high_cc = SymbolIR(
        name="resolve_config",
        qualified_name="sample.resolve_config",
        kind=SymbolKind.FUNCTION,
        span=SourceSpan(
            file=file_path,
            start_line=1,
            start_col=0,
            end_line=4,
            end_col=13,
        ),
        signature=SignatureIR(),
        cyc_complexity=18,
        cog_complexity=18,
        sloc=32,
    )
    structural = RuleFinding(
        rule_id="trivial-wrapper",
        severity=Severity.WARNING,
        message="`resolve_config` adds no behavior",
        span=SourceSpan(
            file=file_path,
            start_line=1,
            start_col=0,
            end_line=4,
            end_col=13,
        ),
        subject_name="resolve_config",
        subject_qualified_name="sample.resolve_config",
        subject_kind=SymbolKind.FUNCTION,
    )
    flags = make_flags(
        clones=[clone_a, clone_b],
        ast_grep_hits=[ast_hit],
        structural_findings=[structural],
        high_cc_functions=[high_cc],
        high_cog_functions=[high_cc],
        total_loc_by_file=[(file_path, 5)],
        all_functions=[high_cc],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4})],
        ast_sloc_lines_by_file=[(file_path, {5})],
        structural_sloc_lines_by_file=[(file_path, {1, 2, 3, 4})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines)

    assert (
        "duplicate-structure: duplicated block (3 lines, 2 instances)" in output
    )
    assert "warning[chained-dict-get]: `.get().get()` chain" in output
    assert "trivial-wrapper[warning]: `resolve_config` adds no behavior" in output
    assert ":5:9" in output
    assert (
        "erosion: function `resolve_config` exceeds complexity threshold"
        in output
    )
    assert (
        "cog_erosion: function `resolve_config` exceeds cognitive complexity threshold"
        in output
    )
    assert "2 │     if args:" in output
    assert '5 │ value = cfg.get("a", {}).get("b", {}).get("c")' in output
    assert "complexity: 18, sloc: 32 (threshold: complexity > 10)" in output
    assert (
        "cognitive complexity: 18, sloc: 32 "
        "(threshold: cognitive complexity > 10)"
        in output
    )


def test_renders_overlapping_ast_hits(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Overlapping ast-grep hits render as separate findings."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def get_cfg_value(cfg):",
                '    value = cfg.get("a", {}).get("b", {}).get("c")',
                "    return value",
            ],
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
    flags = make_flags(
        ast_grep_hits=[chained, empty_dict],
        total_loc_by_file=[(file_path, 3)],
        ast_sloc_lines_by_file=[(file_path, {2})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines, context_lines=1)

    assert output.count("warning[") == 2
    assert output.count("┌─") == 2
    assert "warning[chained-dict-get]: `.get().get()` chain" in output
    assert "warning[dict-get-empty-dict-default]: `d.get(k, {})`" in output
    assert ":2:13" in output
    assert '2 │     value = cfg.get("a", {}).get("b", {}).get("c")' in output
    assert "^" not in output


def test_uses_ast_context(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Ast-grep rendering includes configured surrounding source lines."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def get_cfg_value(cfg):",
                '    value = cfg.get("a", {}).get("b", {}).get("c")',
                "    return value",
            ],
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
    flags = make_flags(
        ast_grep_hits=[ast_hit],
        total_loc_by_file=[(file_path, 3)],
        ast_sloc_lines_by_file=[(file_path, {2})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output_with_zero = render_flags(flags, source_lines, context_lines=0)
    output_with_three = render_flags(flags, source_lines, context_lines=3)

    assert ":2:13" in output_with_zero
    assert "1 │ def get_cfg_value(cfg):" not in output_with_zero
    assert "3 │     return value" not in output_with_zero
    assert "1 │ def get_cfg_value(cfg):" in output_with_three
    assert (
        '2 │     value = cfg.get("a", {}).get("b", {}).get("c")'
        in output_with_three
    )
    assert "3 │     return value" in output_with_three
    assert "^" not in output_with_three


def test_renders_multiline_ast_hit(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Multiline ast-grep hits include every matched source line."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def build():",
                '    value = "\\n".join(',
                '        ["a", "b"]',
                "    )",
                "    return value",
            ],
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
    flags = make_flags(
        ast_grep_hits=[ast_hit],
        total_loc_by_file=[(file_path, 5)],
        ast_sloc_lines_by_file=[(file_path, {2, 3, 4})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines, context_lines=1)

    assert "warning[join-list-literal]" in output
    assert ":2:13" in output
    assert '2 │     value = "\\n".join(' in output
    assert '3 │         ["a", "b"]' in output
    assert "4 │     )" in output
    assert "^" not in output


def test_clone_line_count_and_body_exclude_docstrings(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Clone rendering counts and shows only duplicated SLOC lines."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def first(value):",
                '    """Explain the first helper."""',
                "    current = value + 1",
                "    return current",
                "",
                "def second(value):",
                '    """Explain the second helper."""',
                "    current = value + 2",
                "    return current",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    clone_a = CloneBlock(
        file=file_path,
        start_line=1,
        end_line=4,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 6),),
        first_lines=(
            "def first(value):",
            "    current = value + 1",
            "    return current",
        ),
    )
    clone_b = CloneBlock(
        file=file_path,
        start_line=6,
        end_line=9,
        group_hash="abc123",
        instance_count=2,
        other_instances=((file_path, 1),),
        first_lines=(
            "def second(value):",
            "    current = value + 2",
            "    return current",
        ),
    )
    flags = make_flags(
        clones=[clone_a, clone_b],
        total_loc_by_file=[(file_path, 6)],
        clone_sloc_lines_by_file=[(file_path, {1, 3, 4, 6, 8, 9})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines)

    assert "duplicate-structure: duplicated block (3 lines, 2 instances)" in output
    assert "Explain the first helper" not in output
    assert "Explain the second helper" not in output
    assert "1 │ def first(value):" in output
    assert "3 │     current = value + 1" in output
    assert "6 │ def second(value):" in output
    assert "8 │     current = value + 2" in output


def test_renders_full_clone_span(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Clone rendering includes the full duplicated source span."""
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
            ],
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
    flags = make_flags(
        clones=[clone],
        total_loc_by_file=[(file_path, 6)],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4, 5, 6})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines)

    assert "2 │     value = 1" in output
    assert "6 │     return value" in output


def test_groups_clone_instances(
    tmp_path: Path,
    make_flags: Callable[..., Flags],
) -> None:
    """Clone groups render one summary with each instance location."""
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
            ],
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
    flags = make_flags(
        clones=[clone_a, clone_b],
        total_loc_by_file=[(file_path, 9)],
        clone_sloc_lines_by_file=[(file_path, {2, 3, 4, 7, 8, 9})],
    )
    source_lines = {
        file_path: tuple(file_path.read_text(encoding="utf-8").splitlines()),
    }

    output = render_flags(flags, source_lines)

    assert output.count("duplicate-structure:") == 1
    assert output.count("┌─") == 2
    assert f"┌─ {file_path.as_posix()}:2" in output
    assert f"┌─ {file_path.as_posix()}:7" in output
    assert "other instances:" not in output
    assert "2 │     if args:" in output
    assert "7 │     if args:" in output


def test_empty_flags_render_empty() -> None:
    """No findings render as an empty string."""
    flags = Flags()

    assert render_flags(flags, {}) == ""

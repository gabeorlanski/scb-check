from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.models import AstGrepHit
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze_files


def test_detects_single_return_function_with_cross_file_usages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Single-return functions are reported with resolved project usages."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source_file = _write_source(
        package,
        "api.py",
        '''
        def trivial(value):
            """Legacy wrapper."""
            return value
        ''',
    )
    usage_file = _write_source(
        package,
        "consumer.py",
        """
        from pkg.api import trivial

        RESULT = trivial(VALUE)
        HANDLER = trivial
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file, usage_file))

    wrapper = next(
        finding
        for finding in result.flags.trivial_wrappers
        if finding.name == "trivial"
    )
    assert wrapper.kind == "single_return_function"
    assert wrapper.usage_count == 2
    assert tuple((usage.file, usage.line, usage.kind) for usage in wrapper.usages) == (
        (usage_file, 3, "call"),
        (usage_file, 4, "reference"),
    )
    assert result.flags.trivial_wrapper_sloc_lines_by_file


def test_single_return_functions_returning_constants_are_not_trivial_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Constant-return functions are not removable wrapper findings."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        STATUS = "ready"

        def status():
            return STATUS

        def literal_status():
            return "ready"
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.trivial_wrappers == ()
    assert result.flags.trivial_wrapper_sloc_lines_by_file == ()


def test_single_return_functions_calling_external_functions_are_not_trivial_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """External call adapters are not project wrappers we can safely remove."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        import json

        def parse_payload(value):
            return json.loads(value)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.trivial_wrappers == ()
    assert result.flags.trivial_wrapper_sloc_lines_by_file == ()


def test_required_api_single_return_methods_are_not_trivial_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Properties and inherited API implementations are required surfaces."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        class Resource:
            @property
            def identifier(self):
                return self._identifier

        class JsonEncoder(BaseEncoder):
            def default(self, value):
                return encode_value(value)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.trivial_wrappers == ()
    assert result.flags.trivial_wrapper_sloc_lines_by_file == ()


def test_detects_project_function_passthrough_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Pass-through calls to scanned functions are removable wrappers."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def normalize(value):
            if value:
                return value.strip()
            return ""

        def clean(value):
            return normalize(value)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    wrapper = next(
        finding
        for finding in result.flags.trivial_wrappers
        if finding.name == "clean"
    )
    assert wrapper.kind == "single_return_function"


def test_detects_function_alias_with_cross_file_usages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Aliases to scanned functions are reported as trivial wrappers."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source_file = _write_source(
        package,
        "api.py",
        """
        def real(value):
            if value:
                return value
            return None

        legacy = real
        """,
    )
    usage_file = _write_source(
        package,
        "consumer.py",
        """
        from pkg.api import legacy

        RESULT = legacy(VALUE)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file, usage_file))

    alias = next(
        finding
        for finding in result.flags.trivial_wrappers
        if finding.name == "legacy"
    )
    assert alias.kind == "function_alias"
    assert alias.usage_count == 1
    assert tuple((usage.file, usage.line, usage.kind) for usage in alias.usages) == (
        (usage_file, 3, "call"),
    )


def test_ignore_suppresses_trivial_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directives suppress tree-sitter trivial-wrapper findings."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        # scbc ignore[trivial-wrapper]
        def trivial(value):
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.trivial_wrappers == ()
    assert result.flags.trivial_wrapper_sloc_lines_by_file == ()


def test_trivial_wrapper_ignore_is_valid_without_a_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The tree-sitter trivial-wrapper rule id is valid for source ignores."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        # scbc ignore[trivial-wrapper]
        VALUE = 1
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.total_loc_by_file == ((source_file, 1),)


def test_inline_ignore_suppresses_hit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Inline ignore directives remove matching ast-grep hits and SLOC."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get] boundary normalization for webhook payload
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.ast_grep_hits == ()
    assert result.flags.ast_sloc_lines_by_file == ()


def test_block_ignore_suppresses_hit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Block ignore directives suppress following matching ast-grep hits."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            # scbc ignore[chained-dict-get]
            # boundary normalization for legacy payloads.
            # keep this until the upstream migration is complete.

            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 6, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_ignore_accepts_multiple_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directives can suppress multiple rule IDs."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            # scbc ignore[chained-dict-get,dict-get-empty-dict-default]
            # payload shape is normalized downstream.
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 4, "chained-dict-get"),
            _ast_hit(source_file, 4, "dict-get-empty-dict-default"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_ignore_keeps_unmatched_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directives leave ast-grep hits for other rule IDs."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get] justified boundary behavior
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "chained-dict-get"),
            _ast_hit(source_file, 2, "dict-get-empty-dict-default"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "dict-get-empty-dict-default",
    )


def test_ignore_reason_optional(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directives without a reason still suppress matching hits."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get]
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_comment_ignore_next_code_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Line comment ignores apply to the next code line."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            # scbc ignore[chained-dict-get]
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 3, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_empty_ignore_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Empty ignore directives raise IgnoreDirectiveError."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[] boundary normalization for legacy payload
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    with pytest.raises(
        IgnoreDirectiveError, match="scbc ignore requires at least one rule id",
    ):
        analyze_files((source_file,))


def test_unknown_ignore_rule_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unknown ignored rule IDs raise IgnoreDirectiveError."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[typo-rule] boundary normalization for legacy payload
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    with pytest.raises(
        IgnoreDirectiveError,
        match="unknown ast-grep rule id: typo-rule",
    ):
        analyze_files((source_file,))


def test_wildcard_ignore_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Wildcard ignore directives are not supported."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[*] boundary normalization for legacy payload
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    with pytest.raises(
        IgnoreDirectiveError,
        match="wildcard ignores are not supported",
    ):
        analyze_files((source_file,))


def test_ignore_in_string_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Directive-looking text inside strings is ignored."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            marker = "# scbc ignore[chained-dict-get] reason"
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 3, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "chained-dict-get",
    )


def test_ast_ignore_keeps_other_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignoring ast-grep hits does not suppress clone or complexity findings."""
    fixtures = Path(__file__).parent / "fixtures" / "corpus"
    module_a = _copy_source(tmp_path, fixtures / "module_a.py", "module_a.py")
    module_b = _copy_source(tmp_path, fixtures / "module_b.py", "module_b.py")
    ignored_file = _write_source(
        tmp_path,
        "module_c.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {}).get("c")  # scbc ignore[chained-dict-get] legacy payload normalization
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(ignored_file, 2, "chained-dict-get"),
        ),
    )

    result = analyze_files((module_a, module_b, ignored_file))

    assert result.flags.ast_grep_hits == ()
    assert result.flags.clones
    assert result.flags.high_cc_functions


def test_detects_cross_file_clones(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Analysis reports clone groups that span files."""
    first = _write_source(
        tmp_path,
        "first.py",
        """
        def normalize(value):
            if value:
                return value
            return "fallback"
        """,
    )
    second = _write_source(
        tmp_path,
        "second.py",
        """
        def normalize(value):
            if value:
                return value
            return "fallback"
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((first, second))

    clone_files = {clone.file for clone in result.flags.clones}
    assert clone_files == {first, second}
    assert {clone.instance_count for clone in result.flags.clones} == {2}


def test_dataclass_hits_require_density(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Dataclass-count hits are retained only for dense files."""
    sparse = _write_source(
        tmp_path,
        "sparse.py",
        """
        from dataclasses import dataclass

        @dataclass
        class A:
            x: int
        """,
    )
    dense = _write_source(
        tmp_path,
        "dense.py",
        "\n".join(f"@dataclass\nclass C{i}:\n    x: int\n" for i in range(10)),
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(sparse, 3, "dataclass-count-explosion"),
            *(
                _ast_hit(dense, i * 3 + 1, "dataclass-count-explosion")
                for i in range(10)
            ),
        ),
    )

    result = analyze_files((sparse, dense))

    hit_files = {hit.file for hit in result.flags.ast_grep_hits}
    assert hit_files == {dense}
    assert len(result.flags.ast_grep_hits) == 10


def test_sloc_counts_error_nodes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Analysis still counts SLOC when tree-sitter reports error nodes."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def run():
            return f(a=1, 2)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.total_loc_by_file == ((source_file, 2),)


def test_boundary_suppresses_function_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Boundary directives suppress ast-grep hits inside their function only."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def load_payload(raw):
            # scbc boundary
            value = raw.get("a", {}).get("b", {})
            return value

        def core(raw):
            value = raw.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 3, "chained-dict-get"),
            _ast_hit(source_file, 7, "chained-dict-get"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.line for hit in result.flags.ast_grep_hits) == (7,)


def test_include_all_keeps_boundary_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """include_all preserves hits suppressed by boundary directives."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def load_payload(raw):
            # scbc boundary
            value = raw.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (_ast_hit(source_file, 3, "chained-dict-get"),),
    )

    result = analyze_files((source_file,), include_all=True)

    assert tuple(hit.line for hit in result.flags.ast_grep_hits) == (3,)


def test_include_all_keeps_ignored_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """include_all preserves hits suppressed by ignore directives."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get]
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (_ast_hit(source_file, 2, "chained-dict-get"),),
    )

    result = analyze_files((source_file,), include_all=True)

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "chained-dict-get",
    )


def test_include_all_skips_ignore_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """include_all skips validation for ignored directives."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def get_cfg_value(cfg):
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[]
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (_ast_hit(source_file, 2, "chained-dict-get"),),
    )

    result = analyze_files((source_file,), include_all=True)

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "chained-dict-get",
    )


def test_flags_high_cognitive_complexity_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Analysis flags cognitive complexity with the erosion cutoff."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def nested(a, b, c, d, e):
            if a:
                if b:
                    if c:
                        if d:
                            if e:
                                return 1
            return 0
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.high_cc_functions == ()
    assert tuple(symbol.name for symbol in result.flags.high_cog_functions) == (
        "nested",
    )


def test_boundary_requires_function(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Boundary directives outside functions raise IgnoreDirectiveError."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        # scbc boundary
        value = 1
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    with pytest.raises(
        IgnoreDirectiveError,
        match="scbc boundary must be inside a function body",
    ):
        analyze_files((source_file,))


def _copy_source(tmp_path: Path, source: Path, name: str) -> Path:
    destination = tmp_path / name
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination.resolve()


def _write_source(tmp_path: Path, name: str, source: str) -> Path:
    destination = tmp_path / name
    destination.write_text(dedent(source).strip() + "\n", encoding="utf-8")
    return destination.resolve()


def _ast_hit(file_path: Path, line: int, rule_id: str) -> AstGrepHit:
    return AstGrepHit(
        file=file_path,
        line=line,
        end_line=line,
        col=12,
        end_col=40,
        rule_id=rule_id,
        matched_text='cfg.get("a", {}).get("b", {})',
    )

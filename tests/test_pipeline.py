from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.config import Config
from scb_check.models import AstGrepHit
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze
from scb_check.pipeline import analyze_files


def test_include_all_extends_discovery_to_gitignored_files(tmp_path: Path) -> None:
    """Default discovery respects `.gitignore`; `include_all` scans those files."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    keep = root / "keep.py"
    ignored = root / "ignored.py"
    keep.write_text("x = 1\n", encoding="utf-8")
    ignored.write_text("y = 1\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)

    default_result = analyze(root, config, disable_sg=True)
    include_all_result = analyze(root, config, include_all=True, disable_sg=True)

    assert tuple(path for path, _loc in default_result.flags.lines.total_loc_by_file) == (
        keep.resolve(),
    )
    assert {path for path, _loc in include_all_result.flags.lines.total_loc_by_file} == {
        keep.resolve(),
        ignored.resolve(),
    }


def test_detects_single_return_structural_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Single-return functions are reported as structural findings."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        '''
        def trivial(value):
            """Legacy wrapper."""
            return value
        ''',
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    finding = next(
        finding
        for finding in result.flags.findings.structural_findings
        if finding.subject_name == "trivial"
    )
    assert finding.rule_id == "trivial-wrapper"
    assert finding.message == "`trivial` adds no behavior"
    assert result.flags.lines.structural_sloc_lines_by_file


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

    assert result.flags.findings.structural_findings == ()
    assert result.flags.lines.structural_sloc_lines_by_file == ()


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

    assert result.flags.findings.structural_findings == ()
    assert result.flags.lines.structural_sloc_lines_by_file == ()


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

    assert result.flags.findings.structural_findings == ()
    assert result.flags.lines.structural_sloc_lines_by_file == ()


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

    finding = next(
        finding
        for finding in result.flags.findings.structural_findings
        if finding.subject_name == "clean"
    )
    assert finding.rule_id == "trivial-wrapper"


def test_function_aliases_are_not_structural_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The full cutover reports function wrappers, not alias assignments."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def real(value):
            if value:
                return value
            return None

        legacy = real
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: (),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.structural_findings == ()


def test_ignore_suppresses_trivial_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignore directives suppress structural trivial-wrapper findings."""
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

    assert result.flags.findings.structural_findings == ()
    assert result.flags.lines.structural_sloc_lines_by_file == ()


def test_trivial_wrapper_ignore_is_valid_without_a_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The structural trivial-wrapper rule ID is valid for source ignores."""
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

    assert result.flags.lines.total_loc_by_file == ((source_file, 1),)


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
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[json-loads-read] boundary normalization for webhook payload
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.ast_grep_hits == ()
    assert result.flags.lines.ast_sloc_lines_by_file == ()


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
            # scbc ignore[json-loads-read]
            # boundary normalization for legacy payloads.
            # keep this until the upstream migration is complete.

            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 6, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.ast_grep_hits == ()


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
            # scbc ignore[json-loads-read,duplicated-if-condition]
            # payload shape is normalized downstream.
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 4, "json-loads-read"),
            _ast_hit(source_file, 4, "duplicated-if-condition"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.ast_grep_hits == ()


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
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[json-loads-read] justified boundary behavior
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "json-loads-read"),
            _ast_hit(source_file, 2, "duplicated-if-condition"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.findings.ast_grep_hits) == (
        "duplicated-if-condition",
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
            value = cfg.get("a", {}).get("b", {})  # scbc ignore[json-loads-read]
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.ast_grep_hits == ()


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
            # scbc ignore[json-loads-read]
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 3, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert result.flags.findings.ast_grep_hits == ()


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
        match="unknown rule id: typo-rule",
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
            marker = "# scbc ignore[json-loads-read] reason"
            value = cfg.get("a", {}).get("b", {})
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 3, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.findings.ast_grep_hits) == (
        "json-loads-read",
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
            value = cfg.get("a", {}).get("b", {}).get("c")  # scbc ignore[json-loads-read] legacy payload normalization
            return value
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(ignored_file, 2, "json-loads-read"),
        ),
    )

    result = analyze_files((module_a, module_b, ignored_file))

    assert result.flags.findings.ast_grep_hits == ()
    assert result.flags.findings.clones
    assert result.flags.findings.high_cc_functions


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

    clone_files = {clone.file for clone in result.flags.findings.clones}
    assert clone_files == {first, second}
    assert {clone.instance_count for clone in result.flags.findings.clones} == {2}


def test_count_threshold_hits_require_density(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Count-threshold hits are retained only for dense files."""
    sparse = _write_source(
        tmp_path,
        "sparse.py",
        """
        def sparse():
            return None
        """,
    )
    dense = _write_source(
        tmp_path,
        "dense.py",
        """
        def first():
            return None

        def second():
            return None
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(sparse, 2, "except-return-static-sentinel"),
            _ast_hit(dense, 2, "except-return-static-sentinel"),
            _ast_hit(dense, 5, "except-return-static-sentinel"),
        ),
    )

    result = analyze_files((sparse, dense))

    hit_files = {hit.file for hit in result.flags.findings.ast_grep_hits}
    assert hit_files == {dense}
    assert len(result.flags.findings.ast_grep_hits) == 2


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

    assert result.flags.lines.total_loc_by_file == ((source_file, 2),)


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
            _ast_hit(source_file, 3, "json-loads-read"),
            _ast_hit(source_file, 7, "json-loads-read"),
        ),
    )

    result = analyze_files((source_file,))

    assert tuple(hit.line for hit in result.flags.findings.ast_grep_hits) == (7,)


def test_info_ast_grep_hits_only_show_with_include_all(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Informational ast-grep hits are hidden unless include_all is enabled."""
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def marker(value):
            return None
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg",
        lambda files, rules_path: (
            _ast_hit(source_file, 2, "redundant-return-none"),
            _ast_hit(source_file, 2, "json-loads-read"),
        ),
    )

    default_result = analyze_files((source_file,))
    all_result = analyze_files((source_file,), include_all=True)

    assert tuple(hit.rule_id for hit in default_result.flags.findings.ast_grep_hits) == (
        "json-loads-read",
    )
    assert tuple(hit.rule_id for hit in all_result.flags.findings.ast_grep_hits) == (
        "json-loads-read",
        "redundant-return-none",
    )
    assert tuple(hit.severity for hit in all_result.flags.findings.ast_grep_hits) == (
        "warning",
        "info",
    )


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

    assert tuple(hit.line for hit in result.flags.findings.ast_grep_hits) == (3,)


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

    assert tuple(hit.rule_id for hit in result.flags.findings.ast_grep_hits) == (
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

    assert tuple(hit.rule_id for hit in result.flags.findings.ast_grep_hits) == (
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

    assert result.flags.findings.high_cc_functions == ()
    assert tuple(symbol.name for symbol in result.flags.findings.high_cog_functions) == (
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

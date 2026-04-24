from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.models import AstGrepHit
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze


def test_01(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert result.flags.ast_grep_hits == ()
    assert result.flags.ast_sloc_lines_by_file == ()


def test_02(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_03(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_04(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "dict-get-empty-dict-default",
    )


def test_05(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_06(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert result.flags.ast_grep_hits == ()


def test_07(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    with pytest.raises(
        IgnoreDirectiveError, match="scbc ignore requires at least one rule id"
    ):
        analyze((source_file,))


def test_08(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    with pytest.raises(
        IgnoreDirectiveError,
        match="unknown ast-grep rule id: typo-rule",
    ):
        analyze((source_file,))


def test_09(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    with pytest.raises(
        IgnoreDirectiveError,
        match="wildcard ignores are not supported",
    ):
        analyze((source_file,))


def test_10(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((source_file,))

    assert tuple(hit.rule_id for hit in result.flags.ast_grep_hits) == (
        "chained-dict-get",
    )


def test_11(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((module_a, module_b, ignored_file))

    assert result.flags.ast_grep_hits == ()
    assert result.flags.clones
    assert result.flags.high_cc_functions


def test_12(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    result = analyze((first, second))

    clone_files = {clone.file for clone in result.flags.clones}
    assert clone_files == {first, second}
    assert {clone.instance_count for clone in result.flags.clones} == {2}


def test_13(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    result = analyze((sparse, dense))

    hit_files = {hit.file for hit in result.flags.ast_grep_hits}
    assert hit_files == {dense}
    assert len(result.flags.ast_grep_hits) == 10


def test_14(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_file = _write_source(
        tmp_path,
        "sample.py",
        """
        def run():
            return f(a=1, 2)
        """,
    )

    monkeypatch.setattr(
        "scb_check.pipeline.run_sg", lambda files, rules_path: ()
    )

    result = analyze((source_file,))

    assert result.flags.total_loc_by_file == ((source_file, 2),)


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

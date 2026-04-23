from __future__ import annotations

from conftest import FIXTURES

from scb_check.analysis.clones import detect_clones
from scb_check.analysis.parse import parse_file


def test_detect_clones_returns_instance_flags() -> None:
    source_path = FIXTURES / "corpus" / "module_a.py"
    source, tree = parse_file(source_path)

    clones = detect_clones(((source_path, source, tree),))

    assert clones
    assert all(clone.instance_count >= 2 for clone in clones)
    assert all(
        len(clone.other_instances) == clone.instance_count - 1
        for clone in clones
    )
    assert all(1 <= len(clone.first_lines) <= 3 for clone in clones)

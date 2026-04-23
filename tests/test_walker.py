from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.config import Config
from scb_check.walker import PathError
from scb_check.walker import discover_python_files


def test_discover_python_files_skips_default_excluded_dirs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "__pycache__").mkdir()
    (root / "good.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pkg" / "keep.py").write_text("y = 2\n", encoding="utf-8")
    (root / "node_modules" / "skip.py").write_text("z = 3\n", encoding="utf-8")
    (root / "__pycache__" / "skip2.py").write_text("q = 4\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)
    files = discover_python_files(root, config)

    assert files == tuple(
        sorted(
            [(root / "good.py").resolve(), (root / "pkg" / "keep.py").resolve()]
        )
    )


def test_discover_python_files_applies_user_excludes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    generated = root / "generated"
    pkg = root / "pkg"
    generated.mkdir(parents=True)
    pkg.mkdir(parents=True)
    (generated / "skip.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "keep.py").write_text("y = 1\n", encoding="utf-8")

    config = Config(exclude=("generated/**",), base_dir=root)
    files = discover_python_files(root, config)

    assert files == ((pkg / "keep.py").resolve(),)


def test_discover_python_files_raises_for_missing_path(tmp_path: Path) -> None:
    with pytest.raises(PathError, match="path does not exist"):
        discover_python_files(
            tmp_path / "missing",
            Config(exclude=(), base_dir=tmp_path),
        )


def test_discover_python_files_raises_for_non_python_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")

    with pytest.raises(PathError, match="not a Python file"):
        discover_python_files(source, Config(exclude=(), base_dir=tmp_path))


def test_discover_python_files_raises_for_empty_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty"
    root.mkdir()

    with pytest.raises(PathError, match="no Python files found"):
        discover_python_files(root, Config(exclude=(), base_dir=tmp_path))

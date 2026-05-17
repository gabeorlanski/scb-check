from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.config import Config
from scb_check.walker import walk_python_files
from scb_check.walker import walk_source_files


def test_walk_source_files_discovers_supported_languages(tmp_path: Path) -> None:
    """Source discovery includes every supported language extension."""
    root = tmp_path / "repo"
    root.mkdir()
    supported_names = (
        "python.py",
        "rust.rs",
        "javascript.js",
        "typescript.ts",
        "zig.zig",
        "haskell.hs",
        "cpp.cpp",
    )
    for name in supported_names:
        (root / name).write_text("value = 1\n", encoding="utf-8")
    (root / "notes.txt").write_text("hello\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)
    files = tuple(sorted(walk_source_files(root, config)))

    assert files == tuple(sorted((root / name).resolve() for name in supported_names))


def test_walk_skips_default_dirs(
    tmp_path: Path,
) -> None:
    """Discovery skips default ignored directories."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "__pycache__").mkdir()
    (root / "good.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pkg" / "keep.py").write_text("y = 2\n", encoding="utf-8")
    (root / "node_modules" / "skip.py").write_text("z = 3\n", encoding="utf-8")
    (root / "__pycache__" / "skip2.py").write_text("q = 4\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)
    files = tuple(sorted(walk_python_files(root, config)))

    assert files == tuple(
        sorted(
            [(root / "good.py").resolve(), (root / "pkg" / "keep.py").resolve()],
        ),
    )


def test_walk_applies_excludes(tmp_path: Path) -> None:
    """Discovery applies configured exclude patterns."""
    root = tmp_path / "repo"
    generated = root / "generated"
    pkg = root / "pkg"
    generated.mkdir(parents=True)
    pkg.mkdir(parents=True)
    (generated / "skip.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "keep.py").write_text("y = 1\n", encoding="utf-8")

    config = Config(exclude=("generated/**",), base_dir=root)
    files = tuple(walk_python_files(root, config))

    assert files == ((pkg / "keep.py").resolve(),)


def test_walk_applies_gitignore_globs(tmp_path: Path) -> None:
    """Discovery skips Python files matched by `.gitignore` globs."""
    root = tmp_path / "repo"
    generated = root / "generated"
    pkg = root / "pkg"
    generated.mkdir(parents=True)
    pkg.mkdir(parents=True)
    (root / ".gitignore").write_text(
        "ignored_*.py\ngenerated/\n",
        encoding="utf-8",
    )
    (root / "ignored_module.py").write_text("x = 1\n", encoding="utf-8")
    (generated / "skip.py").write_text("y = 1\n", encoding="utf-8")
    (pkg / "keep.py").write_text("z = 1\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)
    files = tuple(walk_python_files(root, config))

    assert files == ((pkg / "keep.py").resolve(),)


def test_walk_applies_gitignore_negation(tmp_path: Path) -> None:
    """Later `.gitignore` negations re-include matching Python files."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("ignored_*.py\n!ignored_keep.py\n", encoding="utf-8")
    (root / "ignored_drop.py").write_text("x = 1\n", encoding="utf-8")
    (root / "ignored_keep.py").write_text("y = 1\n", encoding="utf-8")

    config = Config(exclude=(), base_dir=root)
    files = tuple(walk_python_files(root, config))

    assert files == ((root / "ignored_keep.py").resolve(),)


def test_walk_missing_path_errors(tmp_path: Path) -> None:
    """Missing discovery paths raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="path does not exist"):
        tuple(
            walk_python_files(
                tmp_path / "missing",
                Config(exclude=(), base_dir=tmp_path),
            ),
        )


def test_walk_non_python_file_errors(
    tmp_path: Path,
) -> None:
    """Non-Python file paths raise ValueError."""
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a Python file"):
        tuple(walk_python_files(source, Config(exclude=(), base_dir=tmp_path)))


def test_walk_allows_empty_dir(
    tmp_path: Path,
) -> None:
    """Empty directories produce no files."""
    root = tmp_path / "empty"
    root.mkdir()

    assert tuple(walk_python_files(root, Config(exclude=(), base_dir=tmp_path))) == ()

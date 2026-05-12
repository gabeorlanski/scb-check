# `scb-check/` — package root

Layers:

- [`tree_walking/`](tree_walking/AGENTS.md) — source text → language-agnostic IR, SLOC, source directives, semantic project context
- [`rules/`](rules/AGENTS.md) — structural rules over tree-walking IR
- [`analysis/`](analysis/AGENTS.md) — ast-grep subprocess integration and clone detection
- [`reporting/`](reporting/AGENTS.md) — findings → output
- [`commands/`](commands/AGENTS.md) — CLI subcommand wiring
- This level — boundaries and shared types

## Modules at this level

- [`cli.py`](cli.py) — top-level Typer app wiring only. Defines the root command group and registers subcommands from [`commands/`](commands/AGENTS.md).
- [`pipeline.py`](pipeline.py) — public `analyze(path, config) -> AnalysisResult` wires path walking, collection, parsing, semantic indexing, ast-grep, structural rules, clone detection, filtering, and `_build_flags`. Tests may use `analyze_files(files)` for focused analysis coverage.
- [`config.py`](config.py), [`walker.py`](walker.py) — IO boundaries. `load_config` walks upward to find `scb_check.toml` or `[tool.scb-check]`, stopping at a `.git` dir. `walk_python_files` is a pathlib-based generator that applies `DEFAULT_EXCLUDED_DIRS`, `.gitignore` globs, and user `exclude` globs (supports `**`).
- [`logging.py`](logging.py) — structlog setup. `configure_logging(verbosity)` runs once from the CLI; modules elsewhere just call `get_logger(__name__)`.
- [`models.py`](models.py) — shared frozen dataclasses for reporting/analysis. Tree-walking IR models live in [`tree_walking/models.py`](tree_walking/models.py).

## Rules

- **Exit codes**: config errors and path errors exit 2 with a message on stderr; parse failures warn and skip the file.
- **New CLI command?** Add it under [`commands/`](commands/AGENTS.md), not as a new top-level module.
- **New module?** Put it in a layer, not here. This directory is for shared boundaries/types — adding more top-level modules blurs the split.
- **Pipeline helpers stay internal.** `Findings` plus `_build_flags` / `_collect_sloc_lines` in `pipeline.py` are implementation details; only `analyze` and `AnalysisResult` are stable entrypoints. If a helper needs reuse elsewhere, move it into a layer first.

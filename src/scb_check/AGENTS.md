# `scb-check/` — package root

Three layers:

- [`analysis/`](analysis/AGENTS.md) — source → findings
- [`reporting/`](reporting/AGENTS.md) — findings → output
- [`commands/`](commands/AGENTS.md) — CLI subcommand wiring
- This level — boundaries and shared types

## Modules at this level

- [`cli.py`](cli.py) — top-level Typer app wiring only. Defines the root command group and registers subcommands from [`commands/`](commands/AGENTS.md).
- [`pipeline.py`](pipeline.py) — single public entrypoint `analyze(files) -> AnalysisResult`. Orchestrates `analysis/` calls and `_build_flags`. CLI and any future consumer should go through this.
- [`config.py`](config.py), [`walker.py`](walker.py) — IO boundaries. `load_config` walks upward to find `scb_check.toml` or `[tool.scb-check]`, stopping at a `.git` dir. `discover_python_files` applies `DEFAULT_EXCLUDED_DIRS` plus user `exclude` globs (supports `**`).
- [`logging.py`](logging.py) — structlog setup. `configure_logging(verbosity)` runs once from the CLI; modules elsewhere just call `get_logger(__name__)`.
- [`models.py`](models.py) — shared frozen dataclasses. Both layers import from here. Don't split these into per-layer models unless a type stops being shared.

## Rules

- **Exit codes**: config errors and path errors exit 2 with a message on stderr; parse failures warn and skip the file.
- **New CLI command?** Add it under [`commands/`](commands/AGENTS.md), not as a new top-level module.
- **New module?** Put it in a layer, not here. This directory is for shared boundaries/types — adding more top-level modules blurs the split.
- **Pipeline helpers stay internal.** `Findings` plus `_build_flags` / `_collect_sloc_lines` in `pipeline.py` are implementation details; only `analyze` and `AnalysisResult` are stable entrypoints. If a helper needs reuse elsewhere, move it into a layer first.

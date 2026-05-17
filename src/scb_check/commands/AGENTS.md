# `commands/` — CLI command boundaries

This package contains Typer subcommand wiring registered by [`../cli.py`](../cli.py).
It is a boundary layer: parse CLI args/options, dispatch to existing modules, and map
errors to exit codes.

## Modules in this layer

- [`check.py`](check.py) — wiring for `scb-check check`.
- [`rule.py`](rule.py) — wiring for `scb-check rule <rule-id>` for ast-grep YAML and structural rule metadata.

## Rules

- **Keep logic at the boundary.** Commands may call [`../config.py`](../config.py), [`../walker.py`](../walker.py), [`../pipeline.py`](../pipeline.py), and [`../reporting/`](../reporting/) but should not reimplement analysis/scoring logic.
- **Keep command callbacks explicit.** Prefer module-level command functions registered from `../cli.py`; use a small registration helper only when a command needs dynamic naming or subcommand grouping.
- **Exit codes stay consistent.** `check` exits `0` when no findings, `1` when any finding (clones, ast-grep hits, structural findings, high-cc/cog functions) is present, and `2` for user-facing config/path/lookup failures printed to stderr.
- **No hidden behavior changes.** Keep command names/options/output contracts stable unless explicitly requested.

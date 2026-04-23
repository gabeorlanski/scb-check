# `commands/` — CLI command boundaries

This package contains Typer subcommand wiring registered by [`../cli.py`](../cli.py).
It is a boundary layer: parse CLI args/options, dispatch to existing modules, and map
errors to exit codes.

## Modules in this layer

- [`check.py`](check.py) — wiring for `scb-check check`.
- [`rule.py`](rule.py) — wiring for `scb-check rule <rule-id>`.

## Rules

- **Keep logic at the boundary.** Commands may call [`../config.py`](../config.py), [`../walker.py`](../walker.py), [`../pipeline.py`](../pipeline.py), and [`../reporting/`](../reporting/) but should not reimplement analysis/scoring logic.
- **One public registration function per module.** Export `register_<command>(app: typer.Typer) -> None` and keep helpers private.
- **Exit codes stay consistent.** User-facing config/path/lookup failures print to stderr and exit with code `2`.
- **No hidden behavior changes.** Keep command names/options/output contracts stable unless explicitly requested.

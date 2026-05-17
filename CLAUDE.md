# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`scb-check` is a Python CLI that reports **verbosity** (clone + slop-pattern LOC share) and **erosion** (high-complexity function mass share) for a Python codebase. Entrypoint: `scb-check check PATH` → [`src/scb_check/cli.py`](src/scb_check/cli.py).

See [README.md](README.md) for user-facing usage.

## Gotchas (read first)

- **`ty` is the type checker, not mypy.** Run `uv run ty check .`.
- **ast-grep subprocess**: `run_sg` tries a global `sg` binary first, then falls back to package-managed ast-grep executables next to Python if global `sg` is missing or fails. Tests monkeypatch `scb_check.pipeline.run_sg` (where it's imported) to avoid this — follow that pattern instead of invoking `sg` in tests.
- **Verbosity is a union**, not a sum. Clone lines ∪ ast-grep lines per file, intersected with SLOC lines. Don't double-count.
- **Dataclasses are `frozen=True, slots=True`** (see [`src/scb_check/models.py`](src/scb_check/models.py)). Pass tuples across module boundaries, not lists.

## Workflow (every change)

1. Write **behavioral** tests — assert observable behavior, not rendering strings or call order.
2. Implement the changes.
3. Follow the workflow:
```bash
uv run ruff check --fix .
uv run ty check .
uv run pytest
uv run scb-check check .            # ty/ruff like reporting
uv run scb-check rule <rule id>     # shows the information for a specific rule
uv run vulture src/
```

4. Update any AGENTS.md files for resources you changed.

Single test: `uv run pytest tests/test_cli.py::test_name`.

## Layout

The package splits into three layers. Before editing in one, read its `AGENTS.md` — those rules win over anything inferred from surrounding code.

- [`src/scb_check/`](src/scb_check/AGENTS.md): Main module for the codebase.
- [`src/scb_check/analysis/`](src/scb_check/analysis/AGENTS.md): source → findings (parse, loc, clones, symbols, astgrep)
- [`src/scb_check/reporting/`](src/scb_check/reporting/AGENTS.md): findings → output (score, render)
- [`src/scb_check/commands`](src/scb_check/commands/AGENTS.md): the command implementations for the CLI.

- Top level (boundaries): [`cli.py`](src/scb_check/cli.py), [`pipeline.py`](src/scb_check/pipeline.py), [`config.py`](src/scb_check/config.py), [`walker.py`](src/scb_check/walker.py), [`logging.py`](src/scb_check/logging.py); shared dataclasses in [`models.py`](src/scb_check/models.py).

Tests mirror this layout: [`tests/analysis/`](tests/analysis/), [`tests/reporting/`](tests/reporting/), and boundary tests at `tests/` root.

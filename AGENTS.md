# AGENTS.md

`scb-check` is a Python CLI that reports **verbosity** (clone + slop-pattern LOC share) and **erosion** (high-complexity function mass share) for supported source codebases. Entrypoint: `scb-check check PATH` → [`src/scb_check/cli.py`](src/scb_check/cli.py).

See [README.md](README.md) for user-facing usage.

See [docs/index.md](docs/index.md) for maintainer guides:

- [Architecture](docs/architecture.md): metrics, pipeline shape, vocabulary, and scoring-sensitive invariants.
- [Tree walking](docs/tree-walking.md): how source becomes IR, directives, semantic context, and rule inputs.
- [Development](docs/development.md): current implementation status and common change approaches.

Keep these docs up to date. When behavior, scoring, CLI contracts, source directives, tree walking, structural rules, reporting, or extension points change, update the relevant guide in the same commit.

## Gotchas (read first)

- **`ty` is the type checker, not mypy.** Run `uv run ty check .`.
- **ast-grep subprocess**: `run_sg` tries a global `sg` binary first, then falls back to package-managed ast-grep executables next to Python if global `sg` is missing or fails. Tests monkeypatch `scb_check.pipeline.run_sg` (where it's imported) to avoid this — follow that pattern instead of invoking `sg` in tests. Python ast-grep rules run only on Python files.
- **Verbosity is a union**, not a sum. Clone lines ∪ ast-grep lines per file, intersected with SLOC lines. Don't double-count. Non-Python languages currently contribute clone LOC only.
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
uv run vulture
```

4. Update affected documentation and AGENTS.md files. Keep README and `docs/` synchronized with current behavior and approaches.

Single test: `uv run pytest tests/test_cli.py::test_name`.

## Layout

The package splits into three layers. Before editing in one, read its `AGENTS.md` — those rules win over anything inferred from surrounding code.

- [`src/scb_check/`](src/scb_check/AGENTS.md): Main module for the codebase.
- [`src/scb_check/analysis/`](src/scb_check/analysis/AGENTS.md): source → findings (parse, loc, clones, symbols, astgrep)
- [`src/scb_check/reporting/`](src/scb_check/reporting/AGENTS.md): findings → output (score, render)
- [`src/scb_check/commands`](src/scb_check/commands/AGENTS.md): the command implementations for the CLI.
- [`docs/`](docs/AGENTS.md): maintainer guides for architecture, tree walking, development status, and change approaches.

- Top level (boundaries): [`cli.py`](src/scb_check/cli.py), [`pipeline.py`](src/scb_check/pipeline.py), [`config.py`](src/scb_check/config.py), [`walker.py`](src/scb_check/walker.py), [`logging.py`](src/scb_check/logging.py); shared dataclasses in [`models.py`](src/scb_check/models.py).

Tests mirror this layout: [`tests/analysis/`](tests/analysis/), [`tests/reporting/`](tests/reporting/), and boundary tests at `tests/` root.

# Philosophy

Pydantic AI is meant to be a light-weight library that any Python developer who wants to work with LLMs and agents (whether simple or complex) should feel no hesitation to pull into their project. It's not meant to be everything to everyone, but it should enable people to build just about anything.

As such, we prefer strong primitives, powerful abstractions, and general solutions and extension points that enable people to build things that we hadn't even thought of, over narrow solutions for specific use cases, opinionated solutions that push a particular approach to agent design that hasn't yet stood the test of time, or generally "every single possible battery included" solutions that make the library unnecessarily bloated.

# Coding Guidelines

When generating or reviewing code anywhere in this repo, always read [agent_docs/index.md](agent_docs/index.md) and follow/enforce those guidelines. Don't forget to read the linked "topic guides" when appropriate.

Additionally, always read the directory-specific instructions when working in those directories:

- [docs/AGENTS.md](docs/AGENTS.md)
- [pydantic_ai_slim/pydantic_ai/AGENTS.md](pydantic_ai_slim/pydantic_ai/AGENTS.md)
- [pydantic_ai_slim/pydantic_ai/builtin_tools/AGENTS.md](pydantic_ai_slim/pydantic_ai/builtin_tools/AGENTS.md)
- [pydantic_ai_slim/pydantic_ai/models/AGENTS.md](pydantic_ai_slim/pydantic_ai/models/AGENTS.md)
- [tests/AGENTS.md](tests/AGENTS.md)
# AGENTS.md

`scb-check` is a Rust CLI that reports **verbosity** (clone + slop-pattern + structural-rule `SLOC` share) and **erosion** (high-complexity function mass share) for supported source codebases. Entrypoint: `scb-check check PATH` -> [crates/scb-check/src/main.rs](crates/scb-check/src/main.rs), with command orchestration in [crates/scb-check/src/lib.rs](crates/scb-check/src/lib.rs).

Python packaging remains only as a wheel delivery mechanism for the compiled Rust binary. The build hook is [hatch_build.py](hatch_build.py); do not reintroduce a Python runtime shim.

See [README.md](README.md) for user-facing usage.

See [docs/index.md](docs/index.md) for maintainer guides:

- [Architecture](docs/architecture.md): metrics, pipeline shape, vocabulary, and scoring-sensitive invariants.
- [Tree walking](docs/tree-walking.md): how source becomes IR, directives, semantic context, and rule inputs.
- [Development](docs/development.md): current implementation status and common change approaches.

Keep these docs up to date. When behavior, scoring, CLI contracts, source directives, tree walking, structural rules, reporting, packaging, or extension points change, update the relevant guide in the same commit.

## Gotchas

- **Rust owns runtime behavior.** The main crate lives at [crates/scb-check](crates/scb-check). Prefer Rust tests and Rust docs for behavior changes.
- **Python packaging is delivery-only.** `pyproject.toml`, `uv.lock`, and `hatch_build.py` exist to build and package the Rust binary for `uvx`.
- **ast-grep runs in process.** Bundled Python ast-grep rules are loaded through Rust ast-grep crates; no external `sg` executable is required for the Rust path.
- **Verbosity is a union**, not a sum. Clone lines union ast-grep lines union structural-rule lines per file, intersected with `SLOC` lines. Do not double-count.
- **Rust and Python source are both parsed by tree-sitter.** Python ast-grep rules currently apply only to Python files; shared structural rules run over lowered Python/Rust facts.
- **Language adapters own language-specific syntax and conventions.** Inside `languages/<language>/`, prefer tree-sitter facts over source text scans for syntax-derived facts. Outside language parsing, core analysis and `rules/` must consume language-agnostic IR facts only, never language-native tree-sitter nodes, syntax kinds, comment markers, visibility conventions, or naming conventions.
- **Avoid Pythonic ports in core logic.** Do not string-scan syntax that tree-sitter can provide, do not model control flow with stringly typed errors, and do not clone owned records just to mimic Python list/dict pipelines.

## Workflow

Every behavior change should start with behavioral tests that assert observable behavior: scores, exit codes, report fields, source discovery, directives, or rendered prefixes.

Run the Rust workflow after Rust changes:

```bash
cargo fmt --check
cargo test --all --all-features
cargo clippy --all --all-targets --all-features -- -D warnings
cargo run -p scb-check -- check .
```

Run the Python packaging workflow after packaging or build-hook changes:

```bash
uv run ruff check hatch_build.py
uv run ty check hatch_build.py
uv run vulture
```

When dependency files change, keep the appropriate lockfile synchronized: `Cargo.lock` for Rust dependencies and `uv.lock` for Python packaging/dev dependencies.

## Layout

The Rust crate is split into boundary, analysis, language, rule, and reporting modules:

- [crates/scb-check/src/main.rs](crates/scb-check/src/main.rs): binary entrypoint.
- [crates/scb-check/src/lib.rs](crates/scb-check/src/lib.rs): CLI orchestration, exit-code mapping, command dispatch.
- [crates/scb-check/src/args.rs](crates/scb-check/src/args.rs): `clap` parsing and CLI option normalization.
- [crates/scb-check/src/config.rs](crates/scb-check/src/config.rs): config discovery and TOML loading.
- [crates/scb-check/src/walk.rs](crates/scb-check/src/walk.rs): source discovery.
- [crates/scb-check/src/analyze.rs](crates/scb-check/src/analyze.rs): report assembly and scoring-sensitive line accounting.
- [crates/scb-check/src/languages/](crates/scb-check/src/languages): tree-sitter parsing, SLOC, complexity, comments, function facts, call facts, and clone fingerprints.
- [crates/scb-check/src/astgrep.rs](crates/scb-check/src/astgrep.rs): bundled and extra ast-grep rule loading/running.
- [crates/scb-check/src/directives.rs](crates/scb-check/src/directives.rs): `scbc` source directives and suppression behavior.
- [crates/scb-check/src/clones.rs](crates/scb-check/src/clones.rs): duplicate-structure detection.
- [crates/scb-check/src/rules/](crates/scb-check/src/rules): structural rules over lowered facts.
- [crates/scb-check/src/render.rs](crates/scb-check/src/render.rs): JSON and human-readable output.
- [crates/scb-check/src/model.rs](crates/scb-check/src/model.rs): shared analysis/reporting records.

Tests are currently colocated with Rust modules. Keep new tests close to the behavior they cover unless an integration test is clearly a better fit.

## Rust Design Expectations

- Boundaries handle coercion and normalization. Core analysis should consume already-validated, strongly typed values.
- Prefer typed errors internally; convert to user-facing strings and exit codes at the CLI boundary.
- In language adapters, derive syntax facts from tree-sitter nodes rather than ad hoc source string parsing; outside adapters, consume lowered language-agnostic facts.
- Move owned values through pipeline stages where possible. Borrow when reading, clone only when ownership must be duplicated.
- Use enums/newtypes for closed sets such as severities, languages, output formats, and rule identifiers when behavior depends on those values.
- Keep scoring-sensitive invariants centralized in analysis/reporting code.
- Composition over inheritance-style abstractions. Add traits only when multiple real implementations need the same interface.
- Never abstract before two real use cases exist.
- No dead code. Version control keeps history.

## agent_docs

When generating or reviewing code anywhere in this repo, always read [agent_docs/index.md](agent_docs/index.md) and follow/enforce those guidelines. Read the linked topic guides when the work touches their area:

- [agent_docs/code-simplification.md](agent_docs/code-simplification.md)
- [agent_docs/api-design.md](agent_docs/api-design.md)
- [agent_docs/documentation.md](agent_docs/documentation.md)

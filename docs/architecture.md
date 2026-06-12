# Architecture

`scb-check` answers one question: **how sloppy is this source codebase?** It reports composite scores plus location-level flags that explain those scores.

## Metrics

### Verbosity

`verbosity` is the share of real source lines of code (`SLOC`) flagged by at least one slop signal.

Per file, flagged lines are the union of:

- clone lines from duplicated syntax blocks in Python or Rust,
- Python `ast-grep` lines from bundled or extra YAML rules,
- structural rule lines from Rust-coded structural rules over shared Python/Rust facts.

Rust currently has no bundled ast-grep pattern rules. JavaScript, TypeScript, Go, Zig, Haskell, and C++ are not first-cutover scan targets.

That union is intersected with `SLOC`, then divided by total `SLOC`. A line flagged by more than one source counts once.

### Erosion

`erosion` is the share of cyclomatic function mass concentrated in high-complexity functions.

- `mass = cyclomatic_complexity * sqrt(sloc)`
- high-complexity functions have `cyclomatic_complexity > 10`
- functions with `sloc <= 0` contribute zero mass

`cog_erosion` uses the same mass-share calculation with cognitive complexity and `cog_complexity > 10`.

## Pipeline

```text
CLI (`crates/scb-check`, via `src/scb_check/cli.py` package shim)
    │
    ├─ load config and discover supported source files
    │
    ▼
`analyze()` in `crates/scb-check/src/analyze.rs`
    │
    ├─ parse Python/Rust source with tree-sitter grammars
    │      └─ emit `SLOC`, functions, call sites, comments, complexity, and clone facts
    ├─ detect clone blocks from normalized parser-derived function bodies
    ├─ run bundled and extra Python `ast-grep` rules through ast-grep crates
    ├─ run Rust-coded structural rules over shared facts
    ├─ apply source ignores, boundary suppression, severity, and thresholds
    └─ build sorted scores and findings
           │
           ├─ JSON scores
           └─ human-readable output
```

## Layers

- Boundary: the Rust crate parses public CLI arguments, loads configuration, walks paths, and renders output. `src/scb_check/cli.py` is only the Python package console-script shim that delegates to the packaged Rust binary.
- Parsing and facts: `crates/scb-check/src/languages/`, `facts.rs`, `directives.rs`, and `analyze.rs` parse already-read Python/Rust source, compute `SLOC`, parse Python source directives, and build shared facts.
- Analysis integrations: `clones.rs` owns normalized clone hashing, and `astgrep.rs` owns in-process ast-grep matching for bundled and extra Python YAML rules.
- Rules: `rules/` owns structural rule metadata, registration, and Rust-coded rule implementations.
- Reporting: `render.rs` turns reports into JSON or human-readable flag text. JSON reports include score summaries plus syntax tree and node counts by parsed language.
- Shared models: `model.rs` contains shared Rust records for source files, functions, findings, syntax summaries, and reports.

## Vocabulary

`SLOC`
: Real source lines of code. Comments, blank lines, punctuation-only delimiter lines in generic parsers, and standalone non-byte, non-f-string Python string statements do not count.

`source directive`
: Python comment directive parsed from tree-sitter comment nodes, such as `# scbc ignore[...]` or `# scbc boundary`.

`boundary suppression`
: `# scbc boundary` inside a function body hides default `ast-grep` findings in that function. Use `--include-all` to show boundary-suppressed findings.

`ast-grep rule`
: Python YAML-backed rule run by ast-grep crates. Extra local rules come from `SCB_CHECK_EXTRA_SLOP_RULES`.

`clone finding`
: Duplicate syntax block found by hashing normalized tree-sitter subtrees. Candidates must contain at least two executable body statements in one duplicated body; signatures, comments, blanks, and Python docstrings do not satisfy that threshold.

`structural rule`
: Rust-coded checker registered in the `rules::Rule` enum. Each checker consumes shared Python/Rust facts and reports diagnostic payloads that implement `Violation`.

`violation`
: Per-rule diagnostic type that owns immutable rule metadata, fix availability, the user-facing message, and optional fix title metadata, following the same separation Ruff uses between rule checks and diagnostics.

`RuleFinding`
: Fixed-field structural finding with rule ID, severity, message, span, and subject metadata.

## Design constraints

- Line numbers are 1-indexed after tree-sitter data leaves the parser layer.
- Supported scan targets are Python (`.py`, `.pyw`) and Rust (`.rs`).
- Python ast-grep rules and source directives are Python-only. Rust-coded structural rules run over any language adapter that provides the needed shared facts.
- Parser-native data may feed clone fingerprints and shared facts, but structural rules do not inspect tree-sitter nodes directly.
- ast-grep runs in process through Rust ast-grep crates. Invalid bundled or extra rules are user-facing errors.
- Source ignores and structural rules share one rule ID namespace, so `scbc ignore[...]` is never ambiguous.
- Clone and erosion findings are not suppressible. `ast-grep` and structural findings are suppressible.
- Shared records cross module boundaries as strict Rust structs and enums.

## Scoring-sensitive surfaces

Change these only with tests and documentation updates because they move user-visible scores:

- parser-derived `SLOC` exclusions in `languages/<language>/parser.rs`,
- clone fingerprint normalization in `languages/mod.rs` and duplicate grouping in `clones.rs`,
- cyclomatic and cognitive complexity node sets in `languages/<language>/parser.rs`,
- sorted and compensated mass summation in `analyze.rs`,
- structural rule span selection and filtering in `rules/`, `directives.rs`, and `analyze.rs`,
- verbosity union logic in `analyze.rs`.

## Extension points

- Extra `ast-grep` rules: set `SCB_CHECK_EXTRA_SLOP_RULES` to a `:`-separated list of YAML files.
- Structural rules: add a Rust rule file in `rules/`, implement a per-rule `Violation`, register it in the `Rule` enum, and keep it on shared facts.
- New public CLI commands: add them to `crates/scb-check`; do not add command logic to the Python shim.

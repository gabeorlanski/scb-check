# Architecture

`scb-check` answers one question: **how sloppy is this source codebase?** It reports composite scores plus location-level flags that explain those scores.

## Metrics

### Verbosity

`verbosity` is the share of real source lines of code (`SLOC`) flagged by at least one slop signal.

Per file, flagged lines are the union of:

- clone lines from duplicated syntax blocks in any supported language,
- Python `ast-grep` lines from bundled or extra YAML rules,
- structural rule lines from Python rule classes.

Rust, JavaScript, TypeScript, Zig, Haskell, and C++ currently have no bundled slop-pattern rules, so their verbosity contribution is clone LOC only.

That union is intersected with `SLOC`, then divided by total `SLOC`. A line flagged by more than one source counts once.

### Erosion

`erosion` is the share of cyclomatic function mass concentrated in high-complexity functions.

- `mass = cyclomatic_complexity * sqrt(sloc)`
- high-complexity functions have `cyclomatic_complexity > 10`
- functions with `sloc <= 0` contribute zero mass

`cog_erosion` uses the same mass-share calculation with cognitive complexity and `cog_complexity > 10`.

## Pipeline

```text
CLI (`cli.py` / `commands/`)
    │
    ├─ load config and discover supported source files
    │
    ▼
`analyze()` in `pipeline.py`
    │
    ├─ parse source with language-specific tree-sitter grammars
    │      └─ emit `ModuleIR`, `SLOC`, symbols, and complexity facts
    ├─ build `ProjectIR` semantic indexes
    ├─ detect clone blocks from parser-native trees
    ├─ run bundled and extra Python `ast-grep` rules through `sg`
    ├─ run structural rules over `ProjectIR`
    ├─ apply source ignores, boundary suppression, severity, and thresholds
    └─ build sorted `Flags`
           │
           ├─ `compute_report()` for JSON scores
           └─ `render_flags()` for human-readable output
```

## Layers

- Boundary: `cli.py`, `commands/`, `config.py`, `walker.py`, and `logging.py` parse arguments, load configuration, walk paths, and wire logging. They do not score code.
- Tree walking: `tree_walking/` parses already-read supported source, computes `SLOC`, parses Python source directives, emits language-agnostic IR, and builds semantic project context. See [Tree walking](tree-walking.md).
- Analysis: `analysis/` owns integrations that intentionally use external or parser-native details: `ast-grep` subprocess execution and clone hashing.
- Rules: `rules/` owns structural rule classes, their registry, metadata, and the runner.
- Reporting: `reporting/` turns `Flags` into JSON reports or human-readable flag text. JSON reports include score summaries plus syntax tree and node counts by parsed language.
- Shared models: `models.py` contains frozen dataclasses shared by analysis, pipeline, and reporting. Tree-walking IR models live in `tree_walking/models.py`.

## Vocabulary

`SLOC`
: Real source lines of code. Comments, blank lines, punctuation-only delimiter lines in generic parsers, and standalone non-byte, non-f-string Python string statements do not count.

`source directive`
: Python comment directive parsed with `tokenize`, such as `# scbc ignore[...]` or `# scbc boundary`.

`boundary suppression`
: `# scbc boundary` inside a function body hides default `ast-grep` findings in that function. Use `--include-all` to show boundary-suppressed findings.

`ast-grep rule`
: Python YAML-backed rule run by the `sg` subprocess. Extra local rules come from `SCB_CHECK_EXTRA_SLOP_RULES`.

`clone finding`
: Duplicate syntax block found by hashing normalized tree-sitter subtrees.

`structural rule`
: Python class in `rules/` that checks typed IR subjects and returns `RuleFinding | None`.

`ModuleIR`
: Pydantic model for a parsed source module. It contains generic symbols, imports, references, operations, source spans, and `SLOC` lines; it does not expose raw tree-sitter nodes.

`SymbolIR`
: Language-agnostic code symbol such as a class, function, method, or value. Function-like symbols carry signatures, roles, body operations, references, `SLOC`, and complexity values.

`ProjectIR`
: Project-level semantic model built from parsed modules. It indexes modules, symbols, files, and derived effects.

`RuleContext`
: Query interface passed to structural rules so rules ask semantic questions instead of inspecting parser-native syntax.

`RuleFinding`
: Fixed-field structural finding with rule ID, severity, message, span, and subject metadata.

## Design constraints

- Line numbers are 1-indexed after tree-sitter data leaves the parser layer.
- Supported scan targets are Python (`.py`, `.pyw`), Rust (`.rs`), JavaScript (`.js`, `.mjs`, `.cjs`), TypeScript (`.ts`), Zig (`.zig`), Haskell (`.hs`), and C++ (`.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`).
- `ast-grep`, structural rules, and source directives are Python-only until language-specific rule sets exist.
- Parser-native data may live on parsed file artifacts for clone detection, but not in `ModuleIR`, `ProjectIR`, or structural rules.
- `ast-grep` failure is non-fatal. A missing `sg` binary, `OSError`, non-zero exit, or invalid JSON returns no hits.
- Source ignores and structural rules share one rule ID namespace, so `scbc ignore[...]` is never ambiguous.
- Clone and erosion findings are not suppressible. `ast-grep` and structural findings are suppressible.
- Immutable records cross module boundaries: frozen dataclasses and Pydantic models, with tuples instead of lists.

## Scoring-sensitive surfaces

Change these only with tests and documentation updates because they move user-visible scores:

- `SLOC` exclusions in `tree_walking/languages/python.py` and `tree_walking/languages/generic.py`,
- `CLONE_NODE_TYPES`, language clone configs, and clone normalization in `analysis/clones.py` plus `tree_walking/languages/*`,
- cyclomatic and cognitive complexity node sets in `tree_walking/languages/python.py` and `tree_walking/languages/*`,
- structural rule span selection and filtering in `rules/` and `pipeline.py`,
- verbosity union logic in `reporting/score.py`.

## Extension points

- Extra `ast-grep` rules: set `SCB_CHECK_EXTRA_SLOP_RULES` to a `:`-separated list of YAML files.
- Structural rules: add a rule class in `rules/`, register it in `rules/registry.py`, and keep it on IR plus `RuleContext`.
- New CLI commands: add command wiring under `commands/` and register from `cli.py`.

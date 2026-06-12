# scb-check

Rust CLI that reports SCBench verbosity and erosion composites for supported source codebases. Python packaging exists only to deliver the compiled Rust binary for `uvx`.

- [Paper](https://arxiv.org/abs/2603.24755)
- [Source](https://github.com/gabeorlanski/scb-check)
- [SlopCodeBench (main repo)](https://github.com/SprocketLab/slop-code-bench)

- **Verbosity**: fraction of SLOC flagged by clone detection, ast-grep slop rules, or structural rules.
- **Erosion**: share of function "mass" (`complexity * sqrt(sloc)`) concentrated in high-complexity functions (cyclomatic complexity > 10).
- **Cognitive erosion**: same mass-share calculation using cognitive complexity > 10.

## Install

Requires Python 3.12+.

Run without installing (recommended):

```bash
uvx scb-check check PATH
uvx --from git+https://github.com/gabeorlanski/scb-check scb-check check PATH
```

Or install into the current project:

```bash
uv sync              # for development in this repo
uv add scb-check     # as a dependency elsewhere
```

Wheels install the compiled Rust binary directly as the `scb-check` script, so `uvx scb-check` runs the Rust CLI without a Python runtime shim.

Bundled ast-grep rules run in process through Rust ast-grep crates. No external `sg` executable is required for the Rust cutover path.

## Usage

```bash
scb-check check PATH                    # human-readable flags
scb-check check PATH --output-format json  # JSON report with verbosity/erosion scores
scb-check check PATH --report           # shortcut for --output-format json
scb-check check PATH -v / --verbosity   # add info logging
scb-check check PATH -vv                # add debug logging
scb-check check PATH --config FILE      # explicit config path
scb-check check PATH --include-all      # include gitignored files plus ignored, lower-severity, and boundary-suppressed findings
scb-check check PATH --disable-sg  # skip ast-grep findings
scb-check check PATH --min-duplicate-lines N  # show duplicate groups with at least N SLOC lines
scb-check rule RULE_ID                  # print YAML or metadata for a specific rule
```

`PATH` may be a file or directory. The first Rust cutover scans Python (`.py`, `.pyw`) and Rust (`.rs`) source files. Directory discovery respects `.gitignore` globs by default; use `--include-all` to scan gitignored supported files too.

### JSON report fields

`verbosity`, `erosion`, `cog_erosion`, `files_scanned`, `total_loc`, `verbosity_flagged_loc`, `clone_loc`, `ast_grep_flagged_loc`, `structural_rule_loc`, `structural_rule_findings`, `total_functions`, `high_cc_functions`, `high_cog_functions`, `total_mass`, `high_cc_mass`, `total_cog_mass`, `high_cog_mass`, `syntax_tree_count`, `syntax_node_count`, and `syntax_by_language`.

`syntax_by_language` is keyed by language value and reports `tree_count` plus total Tree-sitter `node_count` for parsed files in that language.

### Exit codes

`scb-check check` exits `0` when no findings are reported, `1` when any finding is present (clones, ast-grep hits, structural findings, or high-complexity functions), and `2` for usage errors (bad path, missing config, invalid directives).

Clone detection only emits duplicated syntax blocks with at least two executable body statements. Function signatures, comments, blanks, and Python docstrings do not satisfy that threshold; displayed clone line counts and `--min-duplicate-lines` still use duplicated `SLOC` in the clone span.

## Configuration

scb-check looks for `scb-check.toml` or a `pyproject.toml` containing `[tool.scb-check]`, `[tool.ruff]`, or `[tool.ty.src]`, walking upward from the current directory until it hits a `.git` root.

```toml
# scb-check.toml
exclude = ["tests/fixtures/*", "vendor/**"]
context = 1

[low-use-short-function]
enabled = true
max-call-sites = 2
max-function-sloc = 5
max-inline-caller-sloc = 50
max-inline-caller-complexity = 10
max-inline-caller-cognitive-complexity = 10
max-inline-call-nesting = 3
```

```toml
# pyproject.toml
[tool.scb-check]
exclude = ["tests/fixtures/*"]
context = 2

[tool.scb-check.low-use-short-function]
enabled = true
```

- `exclude`: list of glob patterns to skip while discovering supported source files.
- `context`: number of surrounding source lines to show around human-readable ast-grep, structural rule, and erosion findings.
- `low-use-short-function`: opt-in budgets for the short low-use helper rule. Set `enabled = true` to enable it, then tune `max-call-sites`, `max-function-sloc`, `max-inline-caller-sloc`, `max-inline-caller-complexity`, `max-inline-caller-cognitive-complexity`, and `max-inline-call-nesting`.

Configured `exclude` patterns still apply when `--include-all` is used; only `.gitignore` file discovery is extended.

Ast-grep slop rules are currently Python-only. Source directives are parsed from Python and Rust comments. JavaScript, TypeScript, Go, Zig, Haskell, and C++ are outside the first Rust cutover scan target set.

When using `pyproject.toml`, scb-check also includes excludes from:

- `[tool.ruff].exclude`
- `[tool.ruff].extend-exclude`
- `[tool.ty.src].exclude`

## Source directives

In Python and Rust files, you can suppress specific ast-grep or structural rule findings at the source line level with:

```python
# scbc ignore[rule-id]
# scbc ignore[trivial-wrapper]
```

Rust uses the same directive text after `//` or `/* ... */` comments:

```rust
// scbc ignore[trivial-wrapper]
fn identity(value: i32) -> i32 {
    value
}
```

Same-line form:

```python
value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get] Boundary normalization for legacy webhook payloads.
```

Standalone block form:

```python
# scbc ignore[chained-dict-get]
# Boundary normalization for legacy webhook payloads.
value = cfg.get("a", {}).get("b", {})
```

Multiple rule IDs:

```python
# scbc ignore[chained-dict-get,dict-get-empty-dict-default]
# Legacy webhook payloads are partially populated and normalized downstream.
value = cfg.get("a", {}).get("b", {})
```

Function-level boundary suppression is available for code that intentionally validates or normalizes external input:

```python
def _load_toml(path: Path) -> dict[str, Any]:
    # scbc boundary: reads and validates user config
    ...
```

Boundary directives must be inside the function body, after the function signature line. By default, ast-grep findings inside that function are hidden, and informational ast-grep rules are omitted. Use `--include-all` to show ignored, informational, and boundary-suppressed ast-grep findings.

Rules:

- Rule IDs inside `ignore[...]` are required.
- Reason text is optional.
- Same-line ignore directives apply to that same physical line.
- Standalone ignore directives apply to the next non-blank, non-comment code line.
- Boundary directives apply to the containing function body.
- Ast-grep and structural rule findings are suppressible; clone and erosion findings are not.
- Invalid directives fail the run with exit code `2` unless `--include-all` is used.

## How it works

- **Tree walking**: Rust tree-sitter parsing emits shared Python/Rust facts for SLOC, functions, comments, complexity, call sites, and clone fingerprints.
- **Clone detection**: hashed parser-derived function-body fingerprints across the scanned set; two or more matching instances become a `CloneBlock`.
- **Slop patterns**: Python ast-grep rules in `crates/scb-check/src/languages/python/ast_grep_rules/` split by category (e.g. `range(len(x))`, `dict.get(k, None)`, `isinstance` ladders, manual min/max, defensive guards).
- **Structural rules**: Rust-coded structural rules run over shared Python/Rust facts. `trivial-wrapper` flags removable single-return pass-through functions, and `low-use-short-function` flags short helpers with few call sites only when inlining them stays within configured caller SLOC, complexity, cognitive complexity, and nesting budgets.
- **Extra local slop patterns**: set `SCB_CHECK_EXTRA_SLOP_RULES` to a `:`-separated list of YAML paths to layer additional rules on top of the bundled set.
- **Complexity**: per-function cyclomatic and cognitive complexity plus SLOC, combined into mass scores for erosion metrics with stable sorted and compensated summation.

## Documentation

- [Docs index](docs/index.md)
- [Architecture and concepts](docs/architecture.md)
- [Current status and development approach](docs/development.md)

## Development

```bash
uv run ruff check hatch_build.py
uv run ty check hatch_build.py
cargo fmt --check
cargo test --all --all-features
cargo clippy --all --all-targets --all-features -- -D warnings
cargo run -p scb-check -- check .
```

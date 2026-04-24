# Mental Model

`scb-check` answers one question: **how sloppy is this Python codebase?** It does
this by producing two composite numbers between 0 and 1 — *verbosity* and
*erosion* — plus a set of per-location flags that justify those numbers.

## The two metrics

- **Verbosity** = share of SLOC that looks like slop.
  - Union of two signals per file:
    - **Clone lines**: spans covered by a duplicated AST block.
    - **ast-grep lines**: spans covered by a bundled slop rule (e.g.
      `range(len(x))`, `dict.get(k, None)`, `isinstance` ladders).
  - The union is intersected with SLOC (real code lines, not comments/blanks/
    bare-string docstrings), then divided by total SLOC.
  - Lines flagged by *both* sources count once, not twice.

- **Erosion** = share of function "mass" concentrated in complex functions.
  - **Mass** = `cyclomatic_complexity * sqrt(sloc)` per function.
  - Numerator: mass of functions with `complexity > 10`.
  - Denominator: mass of all functions. Functions with `sloc <= 0` contribute 0.

## Pipeline shape

```
CLI (cli.py / commands/)
    │
    ▼
load_config  ─► discover_python_files  ─► analyze(files)
                                              │
                                              ▼
                  ┌───────────────────────────┼─────────────────────────┐
                  │                           │                         │
             parse_file                  run_sg (ast-grep           extract_functions
             sloc_line_numbers            subprocess)               detect_clones
                                         parse_ignore_directives
                  │                           │                         │
                  └───────────────► Findings / Flags ◄──────────────────┘
                                              │
                                              ▼
                       compute_report  (JSON)    render_flags  (human text)
```

Everything above the `Findings` line lives in [`analysis/`](src/scb_check/analysis/).
Everything below lives in [`reporting/`](src/scb_check/reporting/). The
`analyze()` function in [`pipeline.py`](src/scb_check/pipeline.py) is the only
stable entrypoint between them.

## Layered layout

Three layers plus a thin boundary:

- **Boundary** ([`cli.py`](src/scb_check/cli.py),
  [`commands/`](src/scb_check/commands/),
  [`config.py`](src/scb_check/config.py),
  [`walker.py`](src/scb_check/walker.py),
  [`logging.py`](src/scb_check/logging.py)): parses args, loads config, walks
  paths, wires logging. No scoring logic.
- **Analysis** ([`analysis/`](src/scb_check/analysis/)): source → findings.
  Tree-sitter parses files once; downstream analyzers (clones, symbols,
  astgrep, loc, ignores) consume the tree.
- **Reporting** ([`reporting/`](src/scb_check/reporting/)): findings → output.
  Either a `Report` dataclass serialized to JSON (`compute_report`) or
  human-readable `warning[...]:` / `duplicate-structure:` / `erosion:` blocks
  (`render_flags`).
- **Shared types** ([`models.py`](src/scb_check/models.py)): frozen, slotted
  dataclasses. `Flags` aggregates everything reporting needs; `Report` is the
  JSON payload; `CloneBlock` / `AstGrepHit` / `FunctionSymbol` are the
  per-finding records.

## Non-obvious design choices

- **Line numbers are 1-indexed** everywhere past `analysis/`. Tree-sitter
  returns 0-indexed rows; every finding adds `+ 1` on the way out.
- **Single SLOC rule.** `loc.sloc_line_numbers` defines "real code" — it
  strips comments, blank lines, and bare-string expression statements
  (docstrings). Both verbosity's denominator and numerator flow from it.
- **ast-grep never raises.** `run_sg` shells out to the `sg` binary and
  returns `()` on a missing binary, OSError, non-zero exit, or unparseable
  JSON. A missing `sg` degrades gracefully rather than failing the run. Tests
  monkeypatch `scb_check.pipeline.run_sg` rather than the subprocess.
- **Clones are normalized, then hashed.** `_normalize_ast` rewrites
  identifiers to `$VAR1`, `$VAR2`, ... and literals to `$STR`, `$INT`, etc.
  Two blocks are clones iff their normalized AST hashes match. Only node
  types in `CLONE_NODE_TYPES` are considered (function defs, loops, `if`,
  `try`, `with`, `match`), and only blocks spanning ≥ 3 lines.
- **Scoring-sensitive surfaces** should be touched with care:
  `CLONE_NODE_TYPES`, `COMPLEXITY_NODE_TYPES`, `_normalize_ast`, and the
  SLOC exclusion rules. Changing any of them moves every user's numbers.
- **Ignore directives are token-based.** `# scbc ignore[rule-id]` is parsed
  from `tokenize` comment tokens, not raw text. Same-line directives apply
  to that line; standalone directives attach to the next non-blank,
  non-comment code line. Only ast-grep findings are suppressible; clone and
  erosion findings are not.
- **Rule thresholds.** A slop rule's YAML metadata may set
  `min_file_count`; hits in a file below that count are dropped. This is
  how "only flag if you see N of these in one file" rules express themselves.
- **Dataclasses are frozen + slotted.** Pass tuples across module
  boundaries, never lists. `Flags.from_parts` and
  `FileLineSet.from_parts` coerce for you.

## Config discovery

`load_config` walks upward from `cwd` looking for (in order):

1. `scb-check.toml` (dedicated file),
2. `pyproject.toml` containing `[tool.scb-check]`, `[tool.ruff]`, or
   `[tool.ty.src]`.

It stops at a `.git` directory or filesystem root. When a `pyproject.toml`
is used, excludes from `tool.ruff.exclude`, `tool.ruff.extend-exclude`, and
`tool.ty.src.exclude` are merged into scb-check's exclude list so that the
CLI respects the project's existing tool configuration.

## Exit codes

- `0` — ran successfully (flags may still be present).
- `2` — user-facing failure: bad config, bad path, unknown ignore directive,
  no parsable Python files. Message goes to stderr.

Parse failures on individual files warn and skip, never abort the run.

## Extension points

- `SCB_CHECK_EXTRA_SLOP_RULES` — `:`-separated list of YAML files layered
  on top of the bundled rules in
  [`resources/slop_rules/`](src/scb_check/resources/slop_rules/). Read by
  `rule_texts` and combined into a temp file by `rules_file` before `sg` runs.
- New CLI commands: add a `register_<name>(app: typer.Typer)` in
  [`commands/`](src/scb_check/commands/). Don't add top-level modules.

## Testing contract

Tests are organized to mirror the source layers
([`tests/analysis/`](tests/analysis/), [`tests/reporting/`](tests/reporting/),
boundary tests at `tests/` root). They assert on **observable behavior**
(textual prefixes like `duplicate-structure:`, `warning[...]:`, `erosion:`;
JSON report fields; exit codes) rather than call order or internal layout.
`sg` is never actually invoked — tests monkeypatch
`scb_check.pipeline.run_sg`.

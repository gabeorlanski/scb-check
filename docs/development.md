# Development

This guide summarizes the current implementation status and the preferred approach for common changes.

## Current status

`scb-check` is cutting over to a Rust CLI with two public commands:

- `scb-check check PATH` reports human-readable flags or JSON scores.
- `scb-check rule RULE_ID` prints bundled `ast-grep` YAML or structural rule metadata.

`src/scb_check/cli.py` is the public Python package shim that delegates to the Rust binary. The old Python implementation has been removed.

Implemented analysis paths:

- Source discovery for the first-cutover languages: Python (`.py`, `.pyw`) and Rust (`.rs`).
- Tree-sitter parsing into shared function, call-site, SLOC, complexity, comment, and clone facts.
- Parser-derived `SLOC` accounting shared by verbosity, clone line counts, structural spans, and erosion mass.
- Duplicate-structure detection by normalized parser-body hashing for Python and Rust.
- Bundled Python `ast-grep` slop patterns through the Rust ast-grep crates, plus optional local rules from `SCB_CHECK_EXTRA_SLOP_RULES`.
- Rust-coded structural rules over shared Python/Rust facts; the current bundled structural rules are `trivial-wrapper` and opt-in `low-use-short-function`.
- Cyclomatic and cognitive erosion scores for Python and Rust, with sorted and compensated mass summation for stable JSON calculations.
- Python source ignores for `ast-grep` and structural rule IDs.
- Python boundary suppression for validation/normalization functions.

## Runtime contracts

- Exit `0` means the run completed, even when findings were reported.
- Exit `2` is for user-facing failures such as bad config, bad paths, unknown rules, invalid directives, or no discoverable supported source files.
- Individual parse failures warn and skip the file instead of aborting the run.
- Rust files skip Python ast-grep rules and source directives. Structural rules run when the shared facts they need are available.
- Config discovery and source-directive behavior are user-facing; keep README examples synchronized when they change.

## Where to make changes

| Change | Primary location |
| --- | --- |
| Public CLI command or option | `crates/scb-check/src/` |
| Config loading or path walking | `crates/scb-check/src/config.rs`, `crates/scb-check/src/walk.rs` |
| Source parsing, `SLOC`, directives, shared facts | `crates/scb-check/src/parser.rs`, `crates/scb-check/src/directives.rs`, `crates/scb-check/src/analyze.rs` |
| Clone detection | `crates/scb-check/src/clones.rs` |
| `ast-grep` integration | `crates/scb-check/src/astgrep.rs` and `crates/scb-check/resources/slop_rules/` |
| Structural rule behavior | `crates/scb-check/src/rules.rs` |
| JSON scores or human rendering | `crates/scb-check/src/analyze.rs`, `crates/scb-check/src/render.rs` |
| Shared analysis/reporting records | `crates/scb-check/src/model.rs` |

## Adding an `ast-grep` rule

1. Add or update YAML under `crates/scb-check/resources/slop_rules/`.
2. Use a unique rule ID across both `ast-grep` and structural rules.
3. Set severity and any `min_file_count` metadata deliberately.
4. Add behavioral Rust CLI tests that exercise in-process ast-grep matching, severity filtering, count thresholds, directive filtering, and report fields.
5. Update README or docs if the rule changes user-facing behavior or scoring expectations.

## Adding a structural rule

1. Add a Rust rule under `crates/scb-check/src/rules.rs`.
2. Keep rule metadata immutable: `id`, `severity`, `languages`, `target`, and `description`.
3. Operate on shared function/project facts plus `RuleContext`; do not inspect language-native tree-sitter nodes.
4. Register the rule in the Rust structural registry.
5. Ensure the rule ID does not collide with bundled `ast-grep` rule IDs.
6. Test observable findings, ignore behavior, report fields, and rendering prefixes.

## Adding a language

1. Add the tree-sitter grammar dependency.
2. Add a `Language` enum value, parser dispatch, suffix mapping, and discovery coverage in Rust.
3. Add parser lowering for SLOC, functions, complexity, clone fingerprints, comments, and any structural-rule facts the language can provide.
4. Add behavioral parser, clone, and pipeline tests.
5. Document whether ast-grep rules, directives, and structural rules apply to the language.

## Changing scoring

Treat scoring changes as public behavior changes. Update tests first, then implementation, then docs.

Pay special attention to:

- `verbosity` as a union, never a sum,
- `SLOC` as the denominator for verbosity and the source of counted flagged lines,
- Rust verbosity currently includes clone LOC and structural-rule LOC where shared facts prove findings, but not Python ast-grep LOC,
- high-complexity threshold `> 10`,
- mass formulas for `erosion` and `cog_erosion`,
- sorted and compensated float summation for mass totals,
- line spans used by clone, `ast-grep`, and structural findings.

## Verification

Run the project workflow after changes:

```bash
uv run ruff check --fix .
uv run ty check .
uv run pytest
uv run scb-check check .
uv run vulture
```

For Rust cutover changes, also run:

```bash
cargo fmt --check
cargo test -p scb-check
cargo clippy --all-targets -- -D warnings
```

Use focused tests while iterating, then run the full workflow before presenting results. Keep tests behavioral: assert scores, exit codes, report fields, and rendering prefixes instead of internal call order.

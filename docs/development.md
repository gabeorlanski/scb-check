# Development

This guide summarizes the current implementation status and the preferred approach for common changes.

## Current status

`scb-check` is a Python CLI with two public commands:

- `scb-check check PATH` reports human-readable flags or JSON scores.
- `scb-check rule RULE_ID` prints bundled `ast-grep` YAML or structural rule metadata.

Implemented analysis paths:

- Python source discovery for `*.py` files.
- Tree-sitter parsing into language-agnostic IR.
- `SLOC` accounting shared by verbosity, clone line counts, and rule spans.
- Duplicate-structure detection by normalized AST hashing.
- Bundled `ast-grep` slop patterns, plus optional local rules from `SCB_CHECK_EXTRA_SLOP_RULES`.
- Structural rules over `ProjectIR`; the current bundled rule is `trivial-wrapper`.
- Cyclomatic and cognitive erosion scores.
- Source ignores for `ast-grep` and structural rule IDs.
- Boundary suppression for validation/normalization functions.

## Runtime contracts

- Exit `0` means the run completed, even when findings were reported.
- Exit `2` is for user-facing failures such as bad config, bad paths, unknown rules, invalid directives, or no parsable Python files.
- Individual parse failures warn and skip the file instead of aborting the run.
- Config discovery and source-directive behavior are user-facing; keep README examples synchronized when they change.

## Where to make changes

| Change | Primary location |
| --- | --- |
| CLI command or option | `src/scb_check/commands/` |
| Config loading or path walking | `src/scb_check/config.py`, `src/scb_check/walker.py` |
| Source parsing, `SLOC`, directives, IR | `src/scb_check/tree_walking/`; see [Tree walking](tree-walking.md) |
| Clone detection | `src/scb_check/analysis/clones.py` |
| `ast-grep` integration | `src/scb_check/analysis/astgrep.py` and `src/scb_check/resources/slop_rules/` |
| Structural rule behavior | `src/scb_check/rules/` |
| JSON scores or human rendering | `src/scb_check/reporting/` |
| Shared analysis/reporting records | `src/scb_check/models.py` |

## Adding an `ast-grep` rule

1. Add or update YAML under `src/scb_check/resources/slop_rules/`.
2. Use a unique rule ID across both `ast-grep` and structural rules.
3. Set severity and any `min_file_count` metadata deliberately.
4. Add behavioral tests that exercise `pipeline.run_sg` through monkeypatching rather than invoking `sg`.
5. Update README or docs if the rule changes user-facing behavior or scoring expectations.

## Adding a structural rule

1. Add a rule class under `src/scb_check/rules/`.
2. Keep rule metadata immutable: `id`, `severity`, `languages`, `target`, and `description`.
3. Operate on `SymbolIR` or another typed IR subject plus `RuleContext`; do not inspect tree-sitter nodes.
4. Register the rule in `rules/registry.py`.
5. Ensure the rule ID does not collide with bundled `ast-grep` rule IDs.
6. Test observable findings, ignore behavior, report fields, and rendering prefixes.

## Changing scoring

Treat scoring changes as public behavior changes. Update tests first, then implementation, then docs.

Pay special attention to:

- `verbosity` as a union, never a sum,
- `SLOC` as the denominator for verbosity and the source of counted flagged lines,
- high-complexity threshold `> 10`,
- mass formulas for `erosion` and `cog_erosion`,
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

Use focused tests while iterating, then run the full workflow before presenting results. Keep tests behavioral: assert scores, exit codes, report fields, and rendering prefixes instead of internal call order.

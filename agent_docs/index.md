<!-- braindump: rules extracted from PR review patterns, pruned for the Rust scb-check cutover -->

# Coding Guidelines

## Code Style

<!-- rule:409 -->
- Keep PRs focused on their stated purpose. Exclude unrelated cleanup even when it is nearby.
<!-- rule:910 -->
- Wrap code identifiers in backticks in user-facing messages, docs, warnings, and logs.
<!-- rule:193 -->
- Centralize validation at one layer. Boundaries normalize inputs; core logic should trust typed invariants.
<!-- rule:2 -->
- Extract duplicated logic into shared helpers after 2+ real occurrences. Refactor existing code instead of creating parallel implementations.
<!-- rule:341 -->
- Remove commented-out code, unused definitions, and superseded implementations.
<!-- rule:559 -->
- Consolidate duplicate logic across branches using combined conditions, extracted variables, or hoisted shared code.
<!-- rule:14 -->
- Inline single-use helpers that only wrap property access or delegation.
<!-- rule:263 -->
- Extract repeated parsing, scoring, rendering, or path-normalization logic when patterns recur.
<!-- rule:176 -->
- Scope helpers and constants to their single usage site unless reuse is real.
<!-- rule:499 -->
- Reuse static parser/rule metadata where possible. Do not rebuild expensive tree-sitter, ast-grep, or glob state in hot loops.
<!-- rule:1200 -->
- Keep command-boundary, config/walking, analysis, rule, and rendering responsibilities separate.

## Rust Type System

<!-- rule:0 -->
- Use Rust's type system for invariants. Prefer enums, newtypes, and structs over stringly typed control flow.
<!-- rule:142 -->
- Use enums for fixed value sets such as language, severity, output format, command, and rule kind.
<!-- rule:809 -->
- Create small domain types for concepts reused across modules, such as line spans or rule identifiers, when they reduce invalid states or repeated tuple plumbing.
<!-- rule:513 -->
- Type signatures should match runtime reality. Avoid `Option` or broad generic parameters after a boundary has guaranteed presence and shape.
<!-- rule:46 -->
- Fix type and lifetime issues directly. Avoid broad `allow` attributes unless the code has a narrow, documented reason.
<!-- rule:479 -->
- Remove redundant runtime checks once boundary validation or the type system guarantees a condition.
<!-- rule:469 -->
- Prefer borrowing and moving over cloning. Clone only when ownership truly must be duplicated, and keep clones close to the ownership boundary.
<!-- rule:1201 -->
- Shared model structs in `model.rs` are contracts between parser, analysis, reporting, and rules. Keep them explicit, cohesive, and resistant to invalid states.

## Error Handling

<!-- rule:400 -->
- Do not route core control flow through formatted strings. Use typed errors internally and format at the CLI boundary.
<!-- rule:32 -->
- Use precise error messages for user-facing failures; quote arbitrary runtime values clearly.
<!-- rule:353 -->
- Fail fast on explicit user config/directive/path errors; gracefully warn and skip individual parse failures according to the CLI contract.
<!-- rule:320 -->
- Match known error variants explicitly instead of relying on broad catches, string prefixes, or generic buckets.
<!-- rule:1104 -->
- Validate input parameters before expensive operations.
<!-- rule:130 -->
- Trust validated invariants in core logic. Avoid defensive branches that imply impossible states are expected.
<!-- rule:1202 -->
- Preserve CLI exit-code contracts: `0` for no findings, `1` for findings, `2` for usage/config/path/directive/lookup failures.

## Naming

<!-- rule:280 -->
- Drop redundant prefixes when context is clear. Prefer `Report.total_loc` over `Report.report_total_loc`.
<!-- rule:198 -->
- Rename functions and fields when behavior changes; names must reflect actual scope and abstraction level.
<!-- rule:321 -->
- Use semantic names such as `rule_id`, `display_path`, `source_lines`, and `sloc_lines` when multiple concepts are in scope.
<!-- rule:488 -->
- Avoid redundant type suffixes when type is clear from context. Use suffixes only to disambiguate domain concepts.
<!-- rule:770 -->
- Use Rust naming conventions: `SCREAMING_SNAKE_CASE` constants, `snake_case` functions/fields/modules, `UpperCamelCase` types.

## Parsing And Analysis

<!-- rule:1211 -->
- Prefer set operations for line accounting. `SLOC` intersections and clone/ast-grep/structural unions should be expressed directly to avoid double-counting bugs.
<!-- rule:1212 -->
- Prefer tree-sitter node facts over ad hoc string parsing for syntax, parameters, return expressions, call sites, and comments.
<!-- rule:1214 -->
- Keep scoring-sensitive calculations deterministic. Preserve stable sorting and compensated summation unless a scoring change explicitly updates tests and docs.
<!-- rule:1215 -->
- Parse configuration with structured data where practical. Manual TOML traversal should be limited to format selection or compatibility seams.

## Testing

<!-- rule:432 -->
- Remove tests when redundant, obsolete, or duplicative.
<!-- rule:97 -->
- Avoid lint/coverage escape hatches and untested defensive branches. Write tests for reachable behavior.
<!-- rule:1203 -->
- Write behavioral tests that assert scores, exit codes, report fields, source discovery, directive behavior, and rendering prefixes.
<!-- rule:1204 -->
- Prefer Rust unit tests colocated with the module under test. Add integration tests only when command-line behavior across modules is the point.

## Documentation

<!-- rule:272 -->
- Wrap code identifiers in docs and comments with single backticks.
<!-- rule:339 -->
- Remove comments that restate obvious code. Explain non-obvious intent, edge cases, scoring choices, or compatibility constraints.
<!-- rule:35 -->
- Use Markdown heading syntax (`##`, `###`, `####`) instead of bold text for sections.
<!-- rule:396 -->
- Establish one canonical source per topic and link to it.
<!-- rule:138 -->
- Update README, docs, CLI help text, rule descriptions, and AGENTS guidance when functionality or contracts change.
<!-- rule:31 -->
- Use consistent terminology: `verbosity`, `erosion`, `cog_erosion`, `SLOC`, `ast-grep`, `source directive`, `boundary suppression`, and `structural rule`.
<!-- rule:76 -->
- Prefix future work with `TODO:` and link workarounds to upstream/internal issues when possible.
<!-- rule:386 -->
- Keep documentation and implementation in sync.
<!-- rule:150 -->
- Comment non-obvious conditionals, especially error handling, parser quirks, and scoring-sensitive decisions.
<!-- rule:368 -->
- Document what code does now, not what it used to do. Mention Python cutover history only when it explains active packaging compatibility.
<!-- rule:801 -->
- Keep documentation concise and user-facing unless the file is a maintainer guide.
<!-- rule:623 -->
- Avoid line numbers in comments and Rust doc comments because they become stale immediately.

## General

<!-- rule:449 -->
- Use `cargo` for Rust dependency and workflow changes. Use `uv` only for Python packaging/build-hook dependencies.
<!-- rule:1205 -->
- Run the Rust workflow after Rust changes: `cargo fmt --check`, `cargo test --all --all-features`, `cargo clippy --all --all-targets --all-features -- -D warnings`, and `cargo run -p scb-check -- check .`.
<!-- rule:1206 -->
- Run the Python packaging workflow after packaging changes: `uv run ruff check hatch_build.py`, `uv run ty check hatch_build.py`, and `uv run vulture`.

## Topic Guides

Check these when working in specific areas:

- **[Code Simplification & Idioms](code-simplification.md)**: when refactoring code for clarity or looking to simplify complex patterns.
- **[Documentation](documentation.md)**: when writing or updating documentation, comments, CLI help text, or rule descriptions.
- **[API Design & Interfaces](api-design.md)**: when designing or modifying public APIs, command behavior, config, or module boundaries.
<!-- /braindump -->

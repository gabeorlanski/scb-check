<!-- braindump: rules extracted from PR review patterns, pruned for scb-check -->

# Coding Guidelines

## Code Style

<!-- rule:409 -->
- Keep PRs focused on their stated purpose — exclude unrelated changes even if conceptually related — Simplifies review, prevents unintended side effects, and makes rollbacks cleaner when each PR has a single clear objective
<!-- rule:910 -->
- Wrap code identifiers in backticks in user-facing messages, docs, warnings, and logs — Improves readability and clearly distinguishes code elements from prose
<!-- rule:193 -->
- Centralize validation at one layer — removes redundancy and establishes a single source of truth — Prevents validation drift when requirements change and reduces duplicate validation logic across the call chain
<!-- rule:2 -->
- Extract duplicated logic into shared helpers after 2+ occurrences — refactor existing code rather than creating parallel implementations — Prevents bugs from inconsistent implementations and reduces maintenance burden
<!-- rule:341 -->
- Remove commented-out code, unused definitions, and superseded implementations — Version control preserves history; dead code creates confusion about intent and active control flow
<!-- rule:559 -->
- Consolidate duplicate logic across conditional branches using combined conditions, extracted variables, or hoisted shared code — Reduces duplication and clarifies intentionally shared behavior
<!-- rule:14 -->
- Inline single-use helpers that only wrap property access or delegation — reduces nesting and cognitive load without sacrificing clarity
<!-- rule:263 -->
- Extract repeated parsing, scoring, rendering, or path-normalization logic into helper methods or top-level functions when patterns recur — Keeps pipeline behavior consistent across CLI and tests
<!-- rule:176 -->
- Scope helpers and constants to their single usage site — define inline or within the class/function that uses them, not at module level — Reduces namespace pollution and prevents accidental reuse of implementation details
<!-- rule:499 -->
- Compile static regex patterns at module level as constants — avoids recompilation overhead on repeated calls
<!-- rule:1200 -->
- Keep analysis, reporting, and command-boundary responsibilities separate — commands parse CLI input and dispatch; analysis extracts findings; reporting scores and renders

## Type System

<!-- rule:0 -->
- Use `isinstance()` for type checking, not `hasattr()`, `getattr()`, or `type(obj).__name__` checks — Enables proper type narrowing and avoids fragile structural guesses
<!-- rule:142 -->
- Use `Literal` types instead of plain `str` for fixed string value sets in parameters, fields, and return types — Makes valid values explicit and catches invalid strings earlier
<!-- rule:809 -->
- Create type aliases for complex types (3+ union branches, `dict[str, Any] | Callable` patterns, multi-value `Literal`s) or types used 2+ times — Skip aliases for simple one-off internal types
<!-- rule:95 -->
- Use `if TYPE_CHECKING:` blocks for optional dependency types with quoted hints — Keeps package imports lightweight while preserving type safety
<!-- rule:513 -->
- Type signatures should match runtime reality — if control flow or API contracts guarantee only specific types reach a code path, narrow the annotation to exclude impossible types
<!-- rule:46 -->
- Fix type errors properly instead of using broad `# type: ignore` suppressions — use type annotations, narrowing, or `cast()` with explanatory comments when unavoidable
<!-- rule:479 -->
- Remove redundant runtime checks when types already constrain the value — Redundant assertions and duplicate `isinstance()` checks add visual clutter and imply false uncertainty
<!-- rule:469 -->
- Fix type definitions instead of using `cast()` — adjust generics or remove unnecessary unions to match runtime reality; only cast when static analysis cannot express a proven invariant
<!-- rule:494 -->
- Don't add `| None` to `TypedDict` fields marked `total=False` or `NotRequired` — optionality is already expressed by possible omission
<!-- rule:196 -->
- Remove `| None` from type annotations when values are guaranteed to be initialized or always provided — Prevents false optionality and unnecessary checks
<!-- rule:1201 -->
- Keep shared dataclasses frozen and pass tuples across module boundaries — `models.py` types are immutable contracts between analysis, reporting, pipeline, and commands

## Error Handling

<!-- rule:400 -->
- Use `assert` for invariants that should never fail, not generic `RuntimeError('Internal error')` or `pragma: no cover` — Asserts document assumptions and fail fast during development
<!-- rule:32 -->
- Use `!r` for arbitrary runtime values in error messages when exact value boundaries matter — Provides consistent, unambiguous quoting for empty strings and special characters
<!-- rule:353 -->
- Fail fast on explicit user config conflicts; gracefully degrade on optional internal tooling failures — User mistakes should be clear, while missing analysis helpers like `sg` should not crash the whole run
<!-- rule:320 -->
- Catch specific exception types instead of bare `except Exception` when failure modes are known — Prevents hiding unexpected errors and documents expected failure cases
<!-- rule:1104 -->
- Validate input parameters before expensive operations — Fail fast to avoid wasted work and provide faster feedback
<!-- rule:130 -->
- Trust validated invariants and use defaults over defensive assertions — Reduces brittle failures and avoids redundant checks after a boundary has validated input
<!-- rule:1202 -->
- Preserve CLI exit-code contracts — config, path, and lookup errors exit `2`; parse failures warn and skip the file

## Naming

<!-- rule:280 -->
- Drop redundant prefixes when context is clear — prefer `Report.total_loc` over `Report.report_total_loc` and `FunctionSymbol.name` over `FunctionSymbol.function_name`
<!-- rule:198 -->
- Rename methods/functions when their behavior changes — names must reflect actual scope, return values, and abstraction level
<!-- rule:321 -->
- Use specific parameter/variable names that convey semantic meaning — prefer `rule_id`, `display_path`, and `config_data` over generic `id`, `name`, and `data` when multiple concepts are in scope
<!-- rule:488 -->
- Avoid redundant type suffixes (`Value`, `Type`, `Class`, `_dict`, `_list`, `_str`) when type is clear from annotations or context
<!-- rule:770 -->
- Use `UPPER_CASE` for module constants; prefix with `_` if internal (`_MAX_RETRIES`) — Distinguishes public API from implementation details

## Imports

<!-- rule:464 -->
- Place all imports at the top of the file, not inline within functions or test bodies — Ensures dependencies are visible at module load time and follows Python conventions
<!-- rule:77 -->
- Keep optional dependency imports at the boundary that needs them, or guard them with helpful errors — Keeps the package installable while making missing-tool failures understandable
<!-- rule:141 -->
- Remove unused imports — Reduces dependency bloat and keeps module namespaces clean
<!-- rule:223 -->
- Remove duplicate imports — Keep only one declaration per imported item

## Testing

<!-- rule:432 -->
- Remove tests when redundant, obsolete, or duplicative — Each test should verify distinct, valuable behavior that currently exists
<!-- rule:97 -->
- Avoid `# pragma: no cover` — write tests instead. Only use it for truly untestable code paths such as platform branches or defensive guards
<!-- rule:1203 -->
- Write behavioral tests — assert observable behavior and scoring results, not incidental call order or full rendering layouts
<!-- rule:1204 -->
- Monkeypatch `scb_check.pipeline.run_sg` in tests that need ast-grep output — Do not invoke the `sg` subprocess directly in unit tests

## Documentation

<!-- rule:272 -->
- Wrap code identifiers in docstrings with single backticks — parameters, variables, functions, classes, types, fields, and API terms
<!-- rule:339 -->
- Remove comments that restate obvious code — Explain non-obvious intent, edge cases, or constraints instead
<!-- rule:35 -->
- Use Markdown heading syntax (`##`, `###`, `####`) instead of bold text for sections — Preserves semantic structure and document navigation
<!-- rule:396 -->
- Establish one canonical source per topic and link to it — Prevents inconsistent duplicated documentation
<!-- rule:138 -->
- Update all related docs in the same PR when changing functionality, APIs, or capabilities — includes README usage, CLI help, docstrings, comments, slop-rule descriptions, and AGENTS guidance
<!-- rule:31 -->
- Use consistent terminology across code, docs, comments, and errors — Examples: `verbosity`, `erosion`, `SLOC`, `ast-grep`, `source directive`, and `boundary suppression`
<!-- rule:76 -->
- Prefix future work with `TODO:` and link workarounds to upstream/internal issues when possible — Makes technical debt trackable and removable
<!-- rule:386 -->
- Keep documentation and implementation in sync — when they conflict, explicitly decide which to update and fix it
<!-- rule:150 -->
- Comment non-obvious conditionals — Explain edge cases, error handling, scoring choices, and state-based logic
<!-- rule:368 -->
- Document what code does now, not what it used to do — Skip historical references like "original", "old", or "legacy" unless needed for compatibility
<!-- rule:801 -->
- Keep documentation concise — Focus on essential user-facing behavior rather than implementation details that will drift
<!-- rule:623 -->
- Avoid line numbers in comments/docstrings — Use function, class, or rule names instead

## General

<!-- rule:449 -->
- Use `uv` to update dependency locks after dependency changes — Keep `uv.lock` reproducible and avoid unrelated lockfile churn
<!-- rule:1205 -->
- Run the project workflow after code changes: `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest`, `uv run scb-check check .`, and `uv run vulture`

## Topic Guides

Check these when working in specific areas:

- **[Code Simplification & Idioms](code-simplification.md)**: When refactoring code for clarity or looking to simplify complex patterns
- **[Documentation](documentation.md)**: When writing or updating documentation, comments, or docstrings
- **[API Design & Interfaces](api-design.md)**: When designing or modifying public APIs, parameters, or class interfaces
<!-- /braindump -->

# Documentation

> Rules for writing docstrings, comments, user-facing documentation, and maintaining documentation accuracy

**When to check**: When writing or updating documentation, comments, CLI help text, rule descriptions, or docstrings

## Rules

<!-- rule:272 -->
- Wrap all code identifiers in docstrings with single backticks — parameters, variables, functions, classes, types, fields, config keys, CLI options, and rule IDs.
<!-- rule:339 -->
- Remove comments that restate obvious code — Explain non-obvious intent, edge cases, scoring choices, or constraints instead.
<!-- rule:35 -->
- Use Markdown heading syntax (`##`, `###`, `####`) instead of bold text for sections — Preserves semantic document hierarchy and navigation.
<!-- rule:396 -->
- Establish one canonical source per topic and link to it — Documentation duplicated across locations becomes contradictory and harder to maintain.
<!-- rule:34 -->
- Link to official upstream/project docs instead of duplicating exhaustive setup details — Authoritative external docs stay current and reduce maintenance burden.
<!-- rule:138 -->
- Update all related docs in the same PR when changing functionality, APIs, or capabilities — includes README usage, CLI help, docstrings, comments, slop-rule descriptions, and AGENTS guidance.
<!-- rule:31 -->
- Use consistent terminology across code, docs, comments, and errors — Examples: `verbosity`, `erosion`, `SLOC`, `ast-grep`, `source directive`, `boundary suppression`, and `high-complexity function`.
<!-- rule:76 -->
- Prefix future work with `TODO:` and link workarounds to upstream/internal issues when possible — Enables tracking and cleanup when conditions change.
<!-- rule:386 -->
- Keep docs and implementation in sync — When they conflict, explicitly decide which to update and fix it.
<!-- rule:750 -->
- Document defaults comprehensively — Include explicit values, fallback chains, compatibility tradeoffs, and implicit/conditional defaults from parameter interactions.
<!-- rule:150 -->
- Comment non-obvious conditionals — Explain edge cases, error handling, state-based logic, and scoring-sensitive decisions.
<!-- rule:368 -->
- Document what code does now, not what it used to do — Skip historical references like "original", "old", or "legacy" unless they explain an active compatibility constraint.
<!-- rule:801 -->
- Keep documentation concise — Focus on essential user-facing behavior, not implementation details or edge cases that will drift.
<!-- rule:313 -->
- Document workarounds with expected behavior, why it fails, and what external constraint is being compensated for — Prevents future maintainers from removing intentional compatibility code.
<!-- rule:623 -->
- Avoid line numbers in comments/docstrings — Use function, class, module, or rule names instead because line numbers become stale immediately.
<!-- rule:656 -->
- Document new user-facing features where users naturally encounter them — README usage and CLI help are more discoverable than only adding docstrings.
<!-- rule:1213 -->
- Keep source-directive docs synchronized with parser behavior — `scbc ignore[...]`, boundary suppression, and `--include-all` semantics are user-facing contracts.

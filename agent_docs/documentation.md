# Documentation

> Rules for comments, user-facing documentation, CLI help text, rule descriptions, and maintainer guides.

**When to check**: When writing or updating docs, comments, CLI help text, rule metadata, config examples, or source-directive behavior.

## Rules

<!-- rule:272 -->
- Wrap code identifiers with single backticks: functions, types, fields, config keys, CLI options, commands, env vars, rule IDs, and file paths.
<!-- rule:339 -->
- Remove comments that restate obvious code. Explain non-obvious intent, edge cases, scoring choices, parser quirks, or compatibility constraints.
<!-- rule:35 -->
- Use Markdown heading syntax (`##`, `###`, `####`) instead of bold text for sections.
<!-- rule:396 -->
- Establish one canonical source per topic and link to it. Avoid repeating detailed behavior in multiple files.
<!-- rule:34 -->
- Link to official upstream/project docs instead of duplicating exhaustive setup details.
<!-- rule:138 -->
- Update all related docs in the same PR when functionality, CLI contracts, config, scoring, source directives, packaging, or capabilities change.
<!-- rule:31 -->
- Use consistent terminology across code, docs, comments, and errors: `verbosity`, `erosion`, `cog_erosion`, `SLOC`, `ast-grep`, `source directive`, `boundary suppression`, `structural rule`, and `high-complexity function`.
<!-- rule:76 -->
- Prefix future work with `TODO:` and link workarounds to upstream/internal issues when possible.
<!-- rule:386 -->
- Keep docs and implementation in sync. When they conflict, explicitly decide which one is authoritative and update the other.
<!-- rule:750 -->
- Document defaults comprehensively for public config and CLI behavior, including implicit defaults and compatibility aliases.
<!-- rule:150 -->
- Comment non-obvious conditionals, especially around parser behavior, error handling, scoring, and compatibility code.
<!-- rule:368 -->
- Document current behavior. Mention the Python-to-Rust cutover only when it explains active packaging or compatibility behavior.
<!-- rule:801 -->
- Keep documentation concise. README should stay user-facing; `docs/` can hold maintainer detail.
<!-- rule:313 -->
- Document workarounds with expected behavior, why the workaround exists, and what external constraint is being handled.
<!-- rule:623 -->
- Avoid line numbers in comments and docs. Link to files or named functions/types instead.
<!-- rule:656 -->
- Document new user-facing features where users naturally encounter them: README usage, CLI help, config examples, or rule docs.
<!-- rule:1213 -->
- Keep source-directive docs synchronized with parser behavior. `scbc ignore[...]`, boundary suppression, and `--include-all` semantics are public contracts.

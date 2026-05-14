# `docs/`

Documentation in this folder is maintainer-facing.

## Responsibilities

- `index.md` is the docs landing page.
- `architecture.md` is the canonical source for metrics, pipeline shape, vocabulary, and scoring-sensitive invariants.
- `tree-walking.md` is the canonical source for how source text becomes IR, directives, semantic context, and structural-rule inputs.
- `development.md` is the canonical source for current implementation status and common change approaches.

## Rules

- Keep guides concise and current; document what the code does now.
- Keep installation, CLI usage, configuration, and source-directive examples in `README.md`; link there instead of duplicating details.
- Wrap code identifiers, CLI options, rule IDs, and paths in backticks.
- Update these guides whenever behavior, scoring, public commands, or extension points change.

# `rules/` — structural rules

Owns structural rule classes, their static registry, metadata, and the rule runner.

## Invariants

- Rule classes expose immutable class metadata: `id`, `severity`, `languages`, `target`, and `description`.
- Rules operate on typed tree-walking subjects plus `RuleContext`; they must not import tree-sitter or inspect parser-native nodes.
- Rule IDs share one namespace with ast-grep rule IDs for `scbc ignore[...]` validation.
- The runner filters by language and target before invoking rules.

# `tree_walking/` — source → language-agnostic IR

Owns parser dispatch, language walkers, source directives, SLOC lines, pure Pydantic IR models, and semantic project context.

## Invariants

- Language parsers accept already-read source text. File IO stays in boundaries such as `pipeline.py`.
- `ModuleIR`, `SymbolIR`, `OperationIR`, `ValueIR`, `EffectIR`, and `RuleFinding` must not store raw tree-sitter nodes.
- Parser-native data may live only on `ParsedFile` for clone detection.
- SLOC excludes comments, blank lines, and standalone non-f-string/non-bytes string statements.
- Source directives are comment-token based; do not raw-search source text.
- Rules ask `RuleContext` for semantic keep reasons and effects instead of inspecting Python syntax.

# Tree walking

Tree walking turns already-read source into shared facts that scoring, clone detection, structural rules, directives, and reporting can reuse. Language-specific parsing lives in `crates/scb-check/src/languages/<language>/mod.rs`, the shared `BaseParser` and `LanguageParser` contract live in `languages/mod.rs`, directive filtering lives in `directives.rs`, and project assembly lives in `analyze.rs`.

## Boundaries

Parsing does not discover files or read from disk. The CLI boundary discovers Python and Rust source files, reads each file once, then calls the parser with `Language` plus source text.

The parser emits:

- parser-derived `SLOC` lines,
- tree-sitter comments,
- function spans, names, signatures, complexity values, maximum nesting, and clone fingerprints,
- syntax node counts.

Structural rules consume shared facts, not language-native tree-sitter nodes. Add new shared facts only when a scoring path or real rule needs them.

## Parse flow

```text
`walk.rs`
    │
    ├─ discover Python and Rust source files
    │
    ▼
`analyze.rs`
    │
    ├─ read source
    ├─ call `parse_syntax(language, source)`
    ├─ parse source directives from language comment nodes
    ├─ build function facts and clone candidates
    └─ collect project-level scoring inputs
```

Parse failures warn and skip that file. The command fails only when no supported files can be parsed.

## `SLOC`

`SLOC` is computed once by the parser and reused for:

- `total_loc`,
- verbosity denominators,
- clone, ast-grep, and structural line projection,
- function `sloc`,
- erosion mass formulas.

Python SLOC preserves the pre-cutover token behavior with parser data:

1. count leaf token start lines, excluding comments;
2. count string nodes by their start line;
3. remove standalone plain string expression statement ranges when the literal owns the whole line span.

Rust SLOC uses the same generic tree-sitter behavior established during parity work:

1. start from source lines;
2. remove `line_comment` and `block_comment` intervals by line and column;
3. count nonblank lines that are not punctuation-only delimiter lines.

Changing SLOC is scoring-sensitive. Update parity fixtures and docs in the same change.

## Functions

Python `function_definition` and Rust `function_item` nodes become shared function facts.

Function facts include:

- source file and language,
- name, signature, start line, and end line,
- `SLOC` within the function span,
- cyclomatic complexity,
- cognitive complexity,
- maximum nesting,
- conservative bare call sites,
- body shape for structural rules,
- normalized clone fingerprint.

Cyclomatic and cognitive complexity are parser-derived. Mass totals are scored from functions sorted by file, start line, and name, then summed with compensated float accumulation for stable JSON calculations.

## Clone Facts

Clone fingerprints are derived from parser bodies, not raw lines. The normalizer:

- drops comments and standalone plain string statements,
- normalizes identifiers and literals,
- preserves operators and keywords,
- requires executable duplicated body statements before contributing clone LOC.

Clone groups use `blake3` IDs after duplicate bodies are detected.

## Source Directives

Directives are parsed from tree-sitter comment nodes so directive-looking text inside strings is inert. Each language adapter normalizes its own comment syntax before generic directive parsing.

Supported directives:

- `# scbc ignore[rule-id]` or `// scbc ignore[rule-id]`,
- `# scbc boundary` or `// scbc boundary`.

Ignore directives target the same line when they follow code, or the next code line when standalone. Boundary directives suppress ast-grep findings inside the containing function. `--include-all` shows ignored and boundary-suppressed findings.

## Adding Syntax Support

When adding or changing parser support:

- keep IO and path coercion outside parser logic,
- add shared facts only for a concrete scoring or rule need,
- keep structural rules language-agnostic over shared facts,
- update parser, scoring, directive, clone, and JSON regression tests for any scoring-sensitive behavior.

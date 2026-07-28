# Tree walking

Tree walking turns already-read source into shared facts that scoring, clone detection, structural rules, directives, and reporting can reuse. Language-specific parsing lives in `crates/scb-check/src/languages/<language>/mod.rs`, the shared `BaseParser` and `LanguageParser` contract live in `languages/mod.rs`, directive filtering lives in `directives.rs`, and project assembly lives in `analyze.rs`.

## Boundaries

Parsing does not discover files or read from disk. The CLI boundary discovers Python and Rust source files, reads each file once, then calls the parser with `Language`, the source path, and source text.

The parser emits:

- parser-derived `SLOC` lines,
- tree-sitter comments,
- function spans, names, visibility, semantic identity, parser-derived structural facts, complexity values, maximum nesting, and clone fingerprints,
- conservative Python import and Rust use bindings for bare project calls,
- syntax node counts.

Structural rules consume shared facts, not language-native tree-sitter nodes. Add new shared facts only when a scoring path or real rule needs them.

The intended semantic model is deliberately small. Shared facts should capture stable, language-neutral observations such as spans, function boundaries, complexity, nesting, simple-return body facts, typed bare-call scope facts, and conservative resolved call-site relationships. They are not a general name-resolution layer. Bare names can collide across scopes, imports, aliases, methods, and languages, so structural rules must not treat matching identifier text as proof that two references point at the same symbol. When a rule needs stronger evidence, add the narrow semantic fact that proves that relationship, or keep the rule conservative.

Project assembly builds a first-class `CallGraph` from resolved `CallSite` targets. Structural rules that need caller/callee locations should consume that graph instead of rescanning every function or rebuilding call indexes locally. The graph is backed by `petgraph`, but rules use the repo's domain wrapper so graph storage can change without changing rule APIs.

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
    ├─ call `parse_syntax_at_path(language, path, source)`
    ├─ parse source directives from normalized language comment facts
    ├─ build function facts and clone candidates
    ├─ resolve conservative local and explicitly imported call targets
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
- stable function identity from file plus qualified name,
- language-lowered visibility,
- display name, start line, and end line,
- `SLOC` within the function span,
- cyclomatic complexity,
- cognitive complexity,
- maximum nesting,
- conservative bare call sites with parser-derived nesting,
- typed bare-call scope facts for resolving local call relationships,
- resolved local or explicitly imported call targets when the project-level relationship is unique,
- simple-return body facts for structural rules,
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

Ignore directives target the same line when they follow code, or the next code line when standalone. Boundary directives suppress ast-grep findings inside the containing function. Invalid directives always fail the run with exit code `2`. `--include-all` shows ignored and boundary-suppressed findings, but it does not make invalid directives valid.

## Adding Syntax Support

When adding or changing parser support:

- keep IO and path coercion outside parser logic,
- add shared facts only for a concrete scoring or rule need,
- keep structural rules language-agnostic over shared facts,
- keep structural rules off bare-name matching unless another fact makes the relationship semantically safe,
- update parser, scoring, directive, clone, and JSON regression tests for any scoring-sensitive behavior.

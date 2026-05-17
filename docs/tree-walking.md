# Tree walking

Tree walking turns already-read supported source into language-agnostic facts that scoring, structural rules, and reporting can share. It lives in `src/scb_check/tree_walking/`.

## Boundaries

`tree_walking/` does not discover files or read from disk. `pipeline.py` reads source text, then calls `parse_source_file(path, source)` and keeps the returned `ParsedFile` plus the source indexes needed for rendering and Python directive parsing.

`ParsedFile` intentionally has two sides:

- `module`: pure `ModuleIR` for downstream scoring and rules.
- `native_tree`: parser-native data kept only for clone detection.

Do not put raw tree-sitter nodes into `ModuleIR`, `SymbolIR`, `OperationIR`, `ValueIR`, `EffectIR`, or `RuleFinding`.

## Parse flow

```text
`pipeline._parse_source_file()`
    │
    ▼
`dispatch.parse_source_file(path, source)`
    │
    ├─ choose candidate languages from the file suffix
    ├─ apply optional language filters
    └─ try parsers in order
            │
            ▼
`PythonParser.parse()` or `GenericTreeSitterParser.parse()`
    │
    ├─ parse with the language tree-sitter grammar
    ├─ compute `SLOC` lines
    ├─ walk symbols and complexity facts
    └─ return `ParsedFile(source, ModuleIR, native_tree)`
```

A parser raises `LanguageParseError` when it cannot parse source for its own language. Dispatch wraps parser failures in `ProjectParseError`, which `pipeline.py` logs as a warning before skipping that file.

The default dispatch table knows Python (`.py`, `.pyw`), Rust (`.rs`), JavaScript (`.js`, `.mjs`, `.cjs`), TypeScript (`.ts`), Zig (`.zig`), Haskell (`.hs`), and C++ (`.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`). CLI discovery supplies those supported suffixes.

## `SLOC`

`SLOC` is computed once by the parser and then reused everywhere else.

The Python parser:

1. tokenizes source with `tokenize.generate_tokens`,
2. keeps lines with real tokens,
3. drops comments, blanks, indentation-only tokens, and newline-only tokens,
4. removes standalone non-byte, non-f-string string expression statements when the literal owns the full line span.

This is why docstrings do not count as `SLOC`, but meaningful string expressions can still count when they are not plain standalone docstrings.

The generic Tree-sitter parser used for Rust, JavaScript, TypeScript, Zig, Haskell, and C++ starts from non-blank lines, removes comment-only lines from grammar comment nodes including language doc comments such as Haskell `haddock` nodes, and drops punctuation-only delimiter lines such as standalone braces.

## Python walking

`PythonWalker` walks tree-sitter nodes into `ModuleIR`:

- module names come from the path and package `__init__.py` chain,
- spans use 1-indexed lines and 0-indexed columns,
- root-level imports become `ImportIR` records,
- classes and functions become `SymbolIR` records,
- nested classes/functions keep their owner in `owner_qualified_name`,
- module references are aggregated from symbol call references.

Function-like symbols carry:

- `SignatureIR` with parameter names, annotations, and return annotation text,
- body `OperationIR` records for top-level executable body statements,
- call `ReferenceIR` records resolved through imports when possible,
- `SymbolRole` facts for keep reasons,
- `SLOC`, cyclomatic complexity, and cognitive complexity.

The walker only normalizes the facts current rules need. Unknown or unsupported syntax should become `OperationKind.UNKNOWN` or `ValueKind.UNKNOWN`, not parser-native leakage.

## Generic multi-language walking

Rust, JavaScript, TypeScript, Zig, Haskell, and C++ use `GenericTreeSitterParser` with one config per language under `tree_walking/languages/`. The generic parser intentionally emits the minimum IR needed for clone detection and erosion scoring:

- module language, file, span, and `SLOC` lines,
- class-like symbols where the grammar exposes them,
- function and method symbols, including JavaScript and TypeScript generator functions, with names, owners, signatures, spans, `SLOC`, cyclomatic complexity, and cognitive complexity,
- parser-native trees retained on `ParsedFile` for clone hashing and syntax node counts.

It does not yet emit imports, references, body operations, value summaries, or source directives for non-Python languages. Structural rules therefore remain Python-only until they have language-specific semantic facts.

## Operations and values

Body operations are a shallow summary of executable body statements:

- `return`, branch, loop, and `raise` statements map to their matching `OperationKind`,
- expression statements wrapping assignments or calls map to `ASSIGN` or `CALL`,
- anything else maps to `UNKNOWN`.

Return and call operations also carry a `ValueIR`. Values are normalized as invocations, symbol references, member accesses, literals, collections, operators, or `UNKNOWN`. Invocation arguments are recursively normalized so semantic analysis can reason about forwarded parameters and call effects.

## Roles and keep reasons

The parser assigns conservative `SymbolRole` facts:

- dunder methods are `CONTRACT_MEMBER`,
- decorated functions are `CONTRACT_MEMBER`, except `@property`-style decorators become `COMPUTED_ATTRIBUTE`,
- methods on classes with base names are `INHERITED_OVERRIDE`.

Structural rules do not inspect decorators, base-class syntax, or Python nodes directly. They ask `RuleContext` questions such as `is_required_api_surface()`.

## Source directives

Source directives are part of tree walking, but they are parsed separately from `PythonWalker` because they need the full source map and the shared rule namespace.

`directives.py` scans Python comment tokens with `tokenize`; it does not raw-search text. Non-Python files are skipped by directive filtering. It parses:

- `# scbc ignore[rule-id]`, which applies to the same line when it follows code, or to the next non-blank, non-comment code line when standalone,
- `# scbc boundary`, which records the directive line.

`pipeline.py` validates ignore rule IDs against the combined `ast-grep` and structural rule ID namespace. It maps boundary directives to containing function spans before filtering `ast-grep` findings.

## Semantic context

`build_project()` combines parsed modules into `ProjectIR`:

- `symbols_by_qualified_name`,
- `symbols_by_file`,
- derived `EffectIR` records for function-like symbols.

When generic-language function names collide across duplicate basenames or overloads, project indexing appends a source/span suffix to those qualified names so erosion scoring keeps each function distinct.

Effects are derived from normalized operations and values. Invocation values become `PROJECT_CALL`, `EXTERNAL_CALL`, or `UNRESOLVED_CALL`; symbol and member values become `READ`; raise operations become `RAISE`.

`RuleContext` is the structural-rule API over `ProjectIR`. Add a query there when a rule needs a new semantic question, rather than teaching the rule Python syntax.

## Extension rules

- Keep file IO at boundaries; parsers accept `Path` plus already-read source text.
- Keep IR pure and immutable; pass tuples across module boundaries.
- Add parser-native data only to `ParsedFile`, and only when an analysis helper needs it.
- Add enum members or IR fields only when at least one real rule or scoring path needs them.
- When adding syntax support, update parser tests, semantic tests, and any affected scoring docs.
- When adding a new language, add a parser config/module, dispatch mapping, `Language` value, discovery support, clone config, tests, and docs deliberately; do not make Python-specific assumptions in structural rules.

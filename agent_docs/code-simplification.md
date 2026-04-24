# Code Simplification & Idioms

> Rules for simplifying code using Python idioms, comprehensions, operators, and eliminating unnecessary complexity

**When to check**: When refactoring code for clarity or looking to simplify complex patterns

## Rules

<!-- rule:255 -->
- Use list comprehensions instead of for-loop-with-append patterns — More concise, readable, and often faster for transforming/filtering iterables into lists.
<!-- rule:85 -->
- Omit parameters that match default values in function/constructor calls — Reduces noise, prevents maintenance burden when defaults change, and makes non-default configuration more visible.
<!-- rule:166 -->
- Eliminate single-use intermediate variables — Reassign or return directly instead of creating `_filtered`, `_copy`, etc., unless the name adds useful meaning.
<!-- rule:122 -->
- Flatten nested `if` statements with no intervening code into `if condition1 and condition2:` — Reduces nesting depth without changing logic.
<!-- rule:-1 -->
- Use tuple syntax for `isinstance()` checks, not `|` union — Tuple syntax avoids runtime union construction overhead.
<!-- rule:34 -->
- Link to official upstream/project docs instead of duplicating exhaustive setup details — Prevents stale documentation and reduces maintenance burden.
<!-- rule:519 -->
- Use dict comprehensions instead of empty dict plus loop — More concise and idiomatic for simple mappings and filtered sequences.
<!-- rule:330 -->
- Use `any()` instead of for-loops with boolean flags when checking if any element matches a condition — Eliminates manual flag management and break statements.
<!-- rule:677 -->
- Use `@cached_property` for expensive computed attributes — Defers computation until first access and caches the result.
<!-- rule:3 -->
- Use `x or default` for fallback values instead of verbose if-else blocks — Avoid this when falsy values (`0`, `''`, `[]`, `None`) are semantically valid and should not trigger the default.
<!-- rule:661 -->
- Remove redundant null/None checks for guaranteed-present values — Simplifies code and makes type invariants clearer.
<!-- rule:1211 -->
- Prefer set operations for line accounting — SLOC intersections and clone/ast-grep unions should be expressed directly as set operations to avoid double-counting bugs.
<!-- rule:1212 -->
- Reuse module-level singletons for expensive parser/tool setup — Do not rebuild tree-sitter parsers, compiled regexes, or static rule metadata inside hot loops.

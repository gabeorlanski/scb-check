# Code Simplification & Idioms

> Rules for simplifying Rust code and avoiding Python-shaped ports.

**When to check**: When refactoring code for clarity, reducing clone-heavy data flow, or replacing ad hoc parsing.

## Rules

<!-- rule:255 -->
- Prefer iterator adapters when they clarify a straight transform/filter/collect pipeline. Use explicit loops when branching, early exits, or mutation make the loop clearer.
<!-- rule:85 -->
- Omit parameters that match default values in constructors/builders when the default is visible and stable.
<!-- rule:166 -->
- Eliminate single-use intermediate variables unless the name explains domain meaning or makes a scoring step easier to audit.
<!-- rule:122 -->
- Use guard clauses and `let else` to flatten error/empty cases before core logic.
<!-- rule:1216 -->
- Replace string-prefix/sentinel control flow with typed enums or error variants.
<!-- rule:519 -->
- Prefer structured parsing and typed records over `Map<String, Value>` traversal when the shape is known.
<!-- rule:330 -->
- Use `.any()`, `.all()`, `.find()`, and `.position()` instead of manual boolean flags.
<!-- rule:677 -->
- Cache or reuse expensive parser/rule/glob setup when it is independent of the current file.
<!-- rule:3 -->
- Prefer `unwrap_or`, `unwrap_or_default`, and `unwrap_or_else` for simple fallback values. Do not hide meaningful error handling behind defaults.
<!-- rule:661 -->
- Remove redundant `Option` checks after boundary validation has guaranteed presence.
<!-- rule:1211 -->
- Prefer set operations for line accounting. `SLOC` intersections and clone/ast-grep/structural unions should be direct and auditable.
<!-- rule:1212 -->
- Use tree-sitter nodes for syntax-derived facts instead of splitting signatures, scanning lines, or matching source text.
<!-- rule:1217 -->
- Move owned vectors and records between pipeline stages when possible. Avoid cloning whole fact collections just to preserve Python-style append/aggregate flow.

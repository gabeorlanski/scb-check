# API Design & Interfaces

> Rules for designing public APIs, managing visibility, backward compatibility, and CLI-facing contracts

**When to check**: When designing or modifying public APIs, CLI options, command behavior, dataclasses, or module boundaries

## Rules

<!-- rule:1 -->
- Prefix implementation details with underscore (`_`) and exclude them from stable entrypoints — Prevents accidental API surface expansion and signals internal-only usage.
<!-- rule:2 -->
- Prefer instance methods when accessing `self` attributes or enabling polymorphism; use module-level functions when no instance state is needed — Reduces unnecessary coupling and parameter passing.
<!-- rule:3 -->
- Return new collections from transform functions instead of mutating inputs — Prevents surprising side effects and makes code easier to reason about. Exceptions must be performance-critical or clearly named `update_*`/`*_inplace`.
<!-- rule:4 -->
- Don't access or modify private attributes (`_prefixed`) from outside their module/class — Use public APIs, properties, constructor parameters, or move shared logic to an appropriate layer.
<!-- rule:5 -->
- Keep command modules as boundary code — Parse Typer arguments/options, call config/walker/pipeline/reporting modules, and map expected failures to exit codes.
<!-- rule:6 -->
- Preserve CLI contracts unless a change explicitly calls for migration — Command names, option names, JSON field names, and exit codes are user-facing API.
<!-- rule:7 -->
- Keep scoring-sensitive invariants centralized — Verbosity is a union over SLOC lines, erosion is high-complexity mass share, and both belong in reporting/pipeline logic rather than CLI wiring.
<!-- rule:8 -->
- Sparingly define new exception types. If you must keep them broad and ensure they are not just wrappers with pass.
<!-- rule:9 -->
- Minimize use of `tuple` in design. In simple cases it is fine but in large cases a dedicated data structure is preferred.
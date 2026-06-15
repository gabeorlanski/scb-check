# API Design & Interfaces

> Rules for public CLI contracts, Rust module boundaries, config, and shared model design.

**When to check**: When designing or modifying CLI options, command behavior, JSON fields, config, source directives, shared records, or module boundaries.

## Rules

<!-- rule:1 -->
- Keep implementation details module-private unless another module has a real use case. Expose the smallest API that supports current callers.
<!-- rule:2 -->
- Prefer free functions for stateless transforms and small structs for shared state. Add traits only when multiple real implementations need the same interface.
<!-- rule:3 -->
- Make ownership explicit. Return owned data at durable boundaries, borrow for read-only analysis, and consume values when a stage naturally takes ownership.
<!-- rule:4 -->
- Do not reach across module boundaries to manipulate another module's private representation. Move shared behavior to an appropriate public function or type.
<!-- rule:5 -->
- Keep CLI modules as boundary code. `args.rs` parses and normalizes command-line input; `lib.rs` dispatches and maps expected failures to exit codes.
<!-- rule:6 -->
- Preserve public contracts unless a change explicitly includes migration: command names, option names, JSON field names, config keys, source directives, rule IDs, and exit codes.
<!-- rule:7 -->
- Keep scoring-sensitive invariants centralized. `verbosity` is a union over `SLOC` lines; `erosion` and `cog_erosion` are high-complexity mass shares.
<!-- rule:8 -->
- Prefer typed error enums inside Rust modules. Convert to formatted user-facing strings at the CLI boundary.
<!-- rule:9 -->
- Replace large tuples with named structs when values cross function or module boundaries.
<!-- rule:1218 -->
- Use serde structs for known config shapes where practical, including defaults and unknown-field rejection. Keep manual TOML traversal only for format discovery or compatibility behavior.
<!-- rule:1219 -->
- Keep Python packaging APIs isolated to `hatch_build.py` and `pyproject.toml`; do not let packaging constraints leak into Rust core design.

# `analysis/` — source → findings

Parses Python source and extracts structural findings. Tree-sitter based, with stdlib-tokenizer modules for SLOC accounting ([`loc.py`](loc.py)) and ast-grep ignore directives ([`ignores.py`](ignores.py)). Function extraction uses a simple tree visitor in [`symbols.py`](symbols.py) to emit Pydantic [`ParsedSymbol`](../models.py) IR objects. [`trivial_wrappers.py`](trivial_wrappers.py) detects single-return functions and function aliases using shared tree-sitter helpers from [`syntax.py`](syntax.py). Consumed by [`../pipeline.py`](../pipeline.py).

## Invariants

- **Line numbers are 1-indexed at the module boundary.** Tree-sitter exposes 0-indexed `.start_point[0]` — always emit `+ 1` when producing a finding.
- **[`loc.sloc_line_numbers`](loc.py) is the single source of truth for "real" code lines.** It excludes comments, blank lines, and docstrings. Both verbosity intersection and total-LOC derive from it. Do not introduce a second SLOC rule.
- **Parser is a module-level singleton** in [`parse.py`](parse.py). Don't re-instantiate per file.
- **Most findings are frozen dataclasses** from [`../models.py`](../models.py); parsed function symbols are frozen Pydantic models. Emit tuples across the module boundary, never lists.
- **Source directives are comment-token based.** [`ignores.py`](ignores.py) must inspect only `tokenize` comment tokens for `# scbc ignore[...]` and `# scbc boundary`; do not raw-search source text.

## Scoring-sensitive surfaces

These drive the verbosity/erosion numbers — change with care:

- `CLONE_NODE_TYPES` in [`clones.py`](clones.py) — which block types get hashed.
- `_hash_ast_subtree` / `_normalize_ast` — identifier and literal normalization.
- `CYC_COMPLEXITY_NODE_TYPES` and cognitive-complexity flow-break sets in [`symbols.py`](symbols.py) — which nodes count toward complexity.
- SLOC exclusion rules in [`loc.py`](loc.py).
- Trivial-wrapper definition in [`trivial_wrappers.py`](trivial_wrappers.py): single executable `return` functions and aliases to scanned functions.

## ast-grep boundary

[`astgrep.run_sg`](astgrep.py) shells out to the `sg` binary. It returns `()` on missing binary, OSError, non-zero exit, or unparseable JSON — it **never raises**. That's deliberate: a missing `sg` degrades gracefully rather than failing the run. Tests monkeypatch `scb_check.pipeline.run_sg` (where it's imported) rather than the subprocess itself.

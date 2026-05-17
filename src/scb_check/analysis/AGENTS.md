# `analysis/` — external and parser-native finding helpers

This layer keeps analysis that is intentionally separate from generic tree walking:

- [`astgrep.py`](astgrep.py) shells out to the `sg` binary and returns ast-grep hits.
- [`clones.py`](clones.py) uses parser-native tree-sitter data preserved on parsed file artifacts to hash duplicate syntax blocks across supported languages.

Source directives, SLOC accounting, parser dispatch, symbol extraction, string-literal helpers, semantic context, and structural rules live under [`../tree_walking/`](../tree_walking/) and [`../rules/`](../rules/), not here.

## Invariants

- **Line numbers are 1-indexed at the module boundary.** Tree-sitter exposes 0-indexed `.start_point[0]`; clone findings emit `+ 1`.
- **Clone line counts use `ParsedFile.module.sloc_lines`.** Do not reintroduce a second SLOC implementation in this layer.
- **Most findings are frozen dataclasses** from [`../models.py`](../models.py); emit tuples across module boundaries, never lists.

## Scoring-sensitive surfaces

These drive the verbosity/erosion numbers — change with care:

- `CLONE_NODE_TYPES` in [`clones.py`](clones.py) and language clone configs under [`../tree_walking/languages/`](../tree_walking/languages/) — which block types get hashed.
- `_hash_ast_subtree` / `_normalize_ast` — identifier and literal normalization.

## ast-grep boundary

[`astgrep.run_sg`](astgrep.py) shells out to the `sg` binary. It returns `()` on missing binary, OSError, non-zero exit, or unparseable JSON — it **never raises**. That's deliberate: a missing `sg` degrades gracefully rather than failing the run. Tests monkeypatch `scb_check.pipeline.run_sg` (where it's imported) rather than the subprocess itself.

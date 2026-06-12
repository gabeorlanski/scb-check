# `scb-check/` — Python package shim

The old Python implementation has been removed. This package only keeps:

- [`__init__.py`](__init__.py) — package version metadata.
- [`cli.py`](cli.py) — console-script shim that delegates to the Rust binary.
- `bin/scb-check` — packaged wheel binary produced by `hatch_build.py`.

## Rules

- Public CLI behavior belongs in `crates/scb-check`, not Python.
- Keep the shim dependency-free and small.
- Do not add analysis, parsing, reporting, or rule logic back under `src/scb_check`.
- If the shim changes, verify both source-checkout fallback behavior and wheel-installed behavior.

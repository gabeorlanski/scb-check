# `reporting/` — findings → output

Takes a `Flags` object (sorted findings) and produces either a JSON [`Report`](../models.py) or human-readable flag text. Consumed by [`../cli.py`](../cli.py).

## Scoring invariants

- **Verbosity** is the **union** of clone SLOC lines and ast-grep SLOC lines per file, divided by total SLOC. See `_count_union_lines` in [`score.py`](score.py). It is not a sum — lines flagged by both sources count once.
- **Erosion** denominator is the mass of **all** functions; numerator is the mass of functions with `complexity > 10`. Functions with `sloc <= 0` contribute mass 0.
- **Mass** = `complexity * sqrt(sloc)`.
- **`total_loc == 0`** zeroes verbosity and all flagged-LOC counts; **`total_mass == 0`** zeroes erosion. Guard both.

## Rendering

[`render.render_flags`](render.py) emits flags ordered by `(display_path, line, kind_rank)` where kind_rank is clone=0, ast-grep=1, erosion=2. Tests assert on textual markers (e.g. `"duplicate-structure:"`, `"warning[...]:"`, `"erosion: function ..."`), not the exact layout — preserve those prefixes.

Clones are grouped by `group_hash` so each duplicate group renders once, listing every instance inline under a shared `duplicate-structure:` header (separated by `┆`). Don't reintroduce the "other instances:" cross-reference footer — the inline instances replace it. The group is anchored (for ordering) at the earliest `(display_path, start_line)` instance.

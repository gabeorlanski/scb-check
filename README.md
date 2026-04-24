# scb-check

Python CLI that reports SCBench verbosity and erosion composites for a Python codebase.

- [Paper](https://arxiv.org/abs/2603.24755)
- [SlopCodeBench (main repo)](https://github.com/SprocketLab/slop-code-bench)

- **Verbosity**: fraction of SLOC flagged by clone detection or ast-grep slop rules.
- **Erosion**: share of function "mass" (`complexity * sqrt(sloc)`) concentrated in high-complexity functions (cyclomatic complexity > 10).
- **Cognitive erosion**: same mass-share calculation using cognitive complexity > 10.

## Install

Requires Python 3.12+.

Run without installing (recommended):

```bash
uvx scb-check check PATH
uvx --from git+https://github.com/SprocketLab/scb-check scb-check check PATH
```

Or install into the current project:

```bash
uv sync              # for development in this repo
uv add scb-check     # as a dependency elsewhere
```

## Usage

```bash
scb-check check PATH                    # human-readable flags
scb-check check PATH --report           # JSON report with verbosity/erosion scores
scb-check check PATH -v / --verbosity   # add info logging
scb-check check PATH -vv                # add debug logging
scb-check check PATH --config FILE      # explicit config path
scb-check check PATH --include-all      # include ignored and boundary-suppressed ast-grep findings
scb-check rule RULE_ID                  # print YAML for a specific ast-grep rule
```

`PATH` may be a file or directory. Directories are walked for `*.py` files.

### JSON report fields

`verbosity`, `erosion`, `cog_erosion`, `files_scanned`, `total_loc`, `verbosity_flagged_loc`, `clone_loc`, `ast_grep_flagged_loc`, `total_functions`, `high_cc_functions`, `high_cog_functions`, `total_mass`, `high_cc_mass`, `total_cog_mass`, `high_cog_mass`.

## Configuration

scb-check looks for `scb-check.toml` or a `pyproject.toml` containing `[tool.scb-check]`, `[tool.ruff]`, or `[tool.ty.src]`, walking upward from the current directory until it hits a `.git` root.

```toml
# scb-check.toml
exclude = ["tests/fixtures/*", "vendor/**"]
context = 1
```

```toml
# pyproject.toml
[tool.scb-check]
exclude = ["tests/fixtures/*"]
context = 2
```

- `exclude`: list of glob patterns to skip while discovering Python files.
- `context`: number of surrounding source lines to show around human-readable ast-grep and erosion findings.

When using `pyproject.toml`, scb-check also includes excludes from:

- `[tool.ruff].exclude`
- `[tool.ruff].extend-exclude`
- `[tool.ty.src].exclude`

## Source directives

You can suppress specific ast-grep findings at the source line level with:

```python
# scbc ignore[rule-id]
```

Same-line form:

```python
value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get] Boundary normalization for legacy webhook payloads.
```

Standalone block form:

```python
# scbc ignore[chained-dict-get]
# Boundary normalization for legacy webhook payloads.
value = cfg.get("a", {}).get("b", {})
```

Multiple rule IDs:

```python
# scbc ignore[chained-dict-get,dict-get-empty-dict-default]
# Legacy webhook payloads are partially populated and normalized downstream.
value = cfg.get("a", {}).get("b", {})
```

Function-level boundary suppression is available for code that intentionally validates or normalizes external input:

```python
def _load_toml(path: Path) -> dict[str, Any]:
    # scbc boundary: reads and validates user config
    ...
```

Boundary directives must be inside the function body, after the `def` line. By default, ast-grep findings inside that function are hidden. Use `--include-all` to show ignored and boundary-suppressed ast-grep findings.

Rules:

- Rule IDs inside `ignore[...]` are required.
- Reason text is optional.
- Same-line ignore directives apply to that same physical line.
- Standalone ignore directives apply to the next non-blank, non-comment code line.
- Boundary directives apply to the containing function body.
- Only ast-grep findings are suppressible; clone and erosion findings are not.
- Invalid directives fail the run with exit code `2` unless `--include-all` is used.

## How it works

- **Parsing**: tree-sitter-python.
- **Clone detection**: hashed AST blocks across the scanned set; two or more matching instances become a `CloneBlock`.
- **Slop patterns**: ast-grep rules in `src/scb_check/resources/slop_rules/` split by category (e.g. `range(len(x))`, `dict.get(k, None)`, `isinstance` ladders, manual min/max, defensive guards).
- **Extra local slop patterns**: set `SCB_CHECK_EXTRA_SLOP_RULES` to a `:`-separated list of YAML paths to layer additional rules on top of the bundled set.
- **Complexity**: per-function cyclomatic and cognitive complexity plus SLOC, combined into mass scores for erosion metrics.

## Development

```bash
uv run pytest
uv run ruff check
uv run ty check src/
```

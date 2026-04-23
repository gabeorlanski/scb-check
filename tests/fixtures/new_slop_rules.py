"""Fixture exercising newly-added slop rules. Line numbers are asserted
in tests/analysis/test_new_slop_rules.py - keep in sync when editing.

Each block is labeled with the rule id it is meant to exercise plus
FIRES (positive match expected) or MUST NOT FIRE (negative case).

Do not add inline comments on statement lines - ast-grep pattern
matching treats trailing comments as part of the node and they break
pattern matches. Put notes on their own lines above the code.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

# === P1 identity-wrapper-function: FIRES ===


def is_truthy_wrap(value):
    return bool(value)


def parse_expression_wrap(text):
    return ExpressionParser(text).parse()


def annotated_wrap(value: Any) -> bool:
    return bool(value)


# === P1 identity-wrapper-function: MUST NOT FIRE ===


def two_args_not_wrap(a, b):
    return foo(a, b)


def adds_logic_not_wrap(x):
    return foo(x) + 1


def no_args_not_wrap():
    return foo()


class _HasProperty:
    @property
    def thing(self):
        return compute(self)


# === P2 predicate-isinstance-wrapper: FIRES ===


def is_json_object(value: Any) -> bool:
    return isinstance(value, dict)


def is_list_pred(value) -> bool:
    return isinstance(value, list)


# === P2 predicate-isinstance-wrapper: MUST NOT FIRE ===


def not_bool_return(value) -> int:
    return isinstance(value, int)


def has_extra_logic(value) -> bool:
    return isinstance(value, int) and value > 0


# === P3 double-guard-same-value: FIRES ===


def validate_non_empty_string(value, field_path):
    if not isinstance(value, str):
        raise ValueError("must be a non-empty string")
    if not value:
        raise ValueError("must be a non-empty string")
    return value


# === P3 double-guard-same-value: MUST NOT FIRE ===


def single_isinstance_ok(value):
    if not isinstance(value, str):
        raise ValueError("not str")
    return value


def different_vars_ok(a, b):
    if not isinstance(a, str):
        raise ValueError("a")
    if not b:
        raise ValueError("b")


# === P7 dict-from-pairs-loop: FIRES ===


def ordered_obj_fires(pairs):
    o = {}
    for k, v in pairs:
        o[k] = v
    return o


# === P7 dict-from-pairs-loop: MUST NOT FIRE ===


def transforms_value_ok(pairs):
    o = {}
    for k, v in pairs:
        o[k] = str(v)
    return o


def only_one_target_var_ok(pairs):
    o = {}
    for pair in pairs:
        o[pair[0]] = pair[1]
    return o


# === P14 redundant-blank-check: FIRES ===


def process_lines_fires(raw_lines):
    out = []
    for raw_line in raw_lines:
        if raw_line.isspace() or not raw_line:
            continue
        text = raw_line.strip()
        if not text:
            continue
        out.append(text)
    return out


# === P14 redundant-blank-check: MUST NOT FIRE ===


def single_blank_check_ok(raw_lines):
    out = []
    for raw_line in raw_lines:
        text = raw_line.strip()
        if not text:
            continue
        out.append(text)
    return out


# === P15 mutual-isinstance-or-and: FIRES ===


def values_equal_fires(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return (
            isinstance(left, bool) and isinstance(right, bool) and left == right
        )
    return left == right


# === P15 mutual-isinstance-or-and: MUST NOT FIRE ===


def plain_isinstance_ok(left, right):
    if isinstance(left, bool) and isinstance(right, bool):
        return left == right
    return False


# === P18 suffix-slice-removesuffix: FIRES ===


def strip_suffix_bind(segment):
    if segment.endswith(":bind"):
        return segment[: -len(":bind")]
    return segment


def strip_suffix_versions(segment):
    if segment.endswith(":versions"):
        return segment[: -len(":versions")]
    return segment


# === P18 suffix-slice-removesuffix: MUST NOT FIRE ===


def dynamic_len_ok(segment, name):
    return segment[: -len(name)]


def prefix_slice_ok(segment):
    return segment[len(":p") :]


# === P19 update-if-present-dict: FIRES ===


@dataclass(frozen=True)
class _Identity:
    run_id: str | None = None
    cached: bool | None = None
    environment: str | None = None


def with_identity_fires(
    self: _Identity,
    run_id=None,
    cached=None,
    environment=None,
):
    updates = {}
    if run_id is not None:
        updates["run_id"] = run_id
    if cached is not None:
        updates["cached"] = cached
    if environment is not None:
        updates["environment"] = environment
    return replace(self, **updates)


# === P19 update-if-present-dict: MUST NOT FIRE ===


def single_key_update_ok(self, run_id=None):
    updates = {}
    if run_id is not None:
        updates["run_id"] = run_id
    return replace(self, **updates)


# === P21 lambda-generator-throw: FIRES ===


def parse_strict_fires(data):
    return _json_parse(
        data,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


# === P21 lambda-generator-throw: MUST NOT FIRE ===


def normal_lambda_ok(data):
    return _json_parse(data, parse_constant=lambda value: float(value))


# === P22 manual-set-union: FIRES ===


def available_columns_fires(dataset):
    available_cols = set()
    for row in dataset:
        available_cols.update(row.keys())
    return available_cols


# === P22 manual-set-union: MUST NOT FIRE ===


def conditional_update_ok(dataset):
    cols = set()
    for row in dataset:
        if row:
            cols.update(row.keys())
    return cols


def set_add_not_update_ok(items):
    s = set()
    for item in items:
        s.add(item)
    return s


# === P23 fixed-chunk-file-hash: FIRES ===


def sha256_file_fires(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# === P23 fixed-chunk-file-hash: MUST NOT FIRE ===


def while_true_not_hash_ok(path):
    with open(path, "rb") as f:
        while True:
            line = f.readline()
            if not line:
                break
            print(line)


# === P25 oswalk-relpath-sep-replace: FIRES ===


def walk_files_fires(root):
    paths = []
    if not os.path.isdir(root):
        return paths
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for f in filenames:
            if rel_dir == ".":
                rel = f
            else:
                rel = os.path.join(rel_dir, f)
            paths.append(rel.replace(os.sep, "/"))
    paths.sort()
    return paths


# === P25 oswalk-relpath-sep-replace: MUST NOT FIRE ===


def plain_walk_ok(root):
    out = []
    for dirpath, _d, files in os.walk(root):
        for f in files:
            out.append(os.path.join(dirpath, f))
    return out


# === P27 tuple-value-err-caller-unpack: FIRES ===


def parse_scope_fires(raw_scope):
    scope, err_resp = _valid_scope_or_err(raw_scope)
    if err_resp:
        return err_resp
    return scope


# === P27 tuple-value-err-caller-unpack: MUST NOT FIRE ===


def unpack_and_use_both_ok(raw_scope):
    scope, err_resp = _valid_scope_or_err(raw_scope)
    if err_resp:
        log("err", err_resp, scope)
        return None
    return scope


# === MERGE P6 manual-dict-counter-if-else: `.get(k, 0) + 1` form FIRES ===


def count_bad_fires(bad_records):
    bad_counts = {}
    for rec in bad_records:
        kind = rec.get("error", "RUNTIME_ERROR")
        bad_counts[kind] = bad_counts.get(kind, 0) + 1
    return bad_counts


# === MERGE P11 isinstance-return-ladder: 3+-arm cascade FIRES ===


def json_type_cascade_fires(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, str):
        return "string"
    return "other"


# === MERGE P16 sorted-items-default-key: tuple-key form FIRES ===


def sort_tuple_key_fires(unique):
    return tuple(
        unique[k]
        for k in sorted(unique.keys(), key=lambda item: (item[0], item[1]))
    )


# === MERGE P28 verbose-none-default: ternary + self.getter form FIRES ===


class _StateSaver:
    def save_state_fires(
        self,
        items=None,
        categories=None,
    ):
        items = items if items is not None else self.get_items()
        categories = (
            categories if categories is not None else self.get_categories()
        )
        return (items, categories)

    def get_items(self):
        return []

    def get_categories(self):
        return []


# === MERGE P30 repeated-isinstance-validation: trailing `<N raise` FIRES ===


def ensure_positive_int_fires(value, field):
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 1:
        raise ValueError(f"{field} must be >= 1")
    return value


# === Helpers (never meant to match rules) ===


class ExpressionParser:
    def __init__(self, text):
        self.text = text

    def parse(self):
        return self.text


def foo(*args, **kwargs):
    return args


def compute(obj):
    return obj


def _json_parse(data, parse_constant=None):
    return (data, parse_constant)


def _valid_scope_or_err(raw_scope):
    if not raw_scope:
        return None, "bad"
    return raw_scope, None


def log(*args, **kwargs):
    return None


_ = re.compile
_ = base64.b64decode

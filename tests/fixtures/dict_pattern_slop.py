"""Fixture exercising dict-pattern rules. Line numbers are asserted in
tests/analysis/test_dict_pattern_rules.py - keep in sync when editing.

Trailing comments on match lines can break ast-grep matching, so case
markers are placed above each case.
"""

from __future__ import annotations


def do(*_a):
    pass


# === manual-dict-setdefault ===


# CASE: manual_setdefault_strict / fires manual-dict-setdefault
def case_manual_setdefault_strict(d, k, v):
    if k not in d:
        d[k] = v


# CASE: manual_setdefault_extra_stmt / negative
# There is extra work in the guarded block, so setdefault is not equivalent.
def case_manual_setdefault_extra_stmt(d, k, v):
    if k not in d:
        do()
        d[k] = v


# CASE: manual_setdefault_different_key / negative
def case_manual_setdefault_different_key(d, k, v):
    if k not in d:
        d["other"] = v


# === get-then-none-check ===


# CASE: get_then_is_none / fires get-then-none-check
def case_get_then_is_none(d, k):
    value = d.get(k)
    if value is None:
        return 0
    return value


# CASE: get_then_is_not_none / negative
# Presence checks (`is not None`) after `.get(...)` are common and not covered.
def case_get_then_is_not_none(d, k):
    value = d.get(k)
    if value is not None:
        return value
    return 0


# CASE: get_then_default_arg / negative
# .get has a default arg, so this is not the strict None-sentinel shape.
def case_get_then_default_arg(d, k):
    value = d.get(k, 0)
    if value is None:
        return 0
    return value


# CASE: get_then_non_adjacent / negative
def case_get_then_non_adjacent(d, k):
    value = d.get(k)
    do()
    if value is None:
        return 0
    return value


# CASE: get_then_different_var / negative
def case_get_then_different_var(d, k, other):
    value = d.get(k)
    if other is None:
        return 0
    return value

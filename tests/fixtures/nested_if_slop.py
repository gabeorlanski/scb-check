"""Fixture exercising nested-if rules. Line numbers are asserted in
tests/analysis/test_nested_if_rules.py - keep in sync when editing.

Trailing comments on `if` lines break ast-grep pattern matching, so
markers are placed above each case using `# CASE:` headers.
"""

from __future__ import annotations


def do(*_a):
    pass


def other(*_a):
    pass


def cond(_x):
    return False


# === nested-if-no-else: outer body is exactly the nested if ===


# CASE: strict / fires nested-if-no-else
def case_strict(a, b):
    if a:
        if b:
            do()


# CASE: strict_multi_inner_body / fires nested-if-no-else
def case_strict_multi_inner_body(a, b):
    if a:
        if b:
            do()
            do(1)


# === false positives for nested-if-no-else (must NOT fire) ===


# CASE: outer_has_trailing / negative
def case_outer_has_trailing(a, b):
    if a:
        if b:
            do()
        other()


# CASE: outer_has_leading / negative
def case_outer_has_leading(a, b):
    if a:
        other()
        if b:
            do()


# CASE: outer_has_else / negative
def case_outer_has_else(a, b):
    if a:
        if b:
            do()
    else:
        other()


# CASE: inner_has_else / negative
def case_inner_has_else(a, b):
    if a:
        if b:
            do()
        else:
            other()


# CASE: inner_has_elif / negative
def case_inner_has_elif(a, b, c):
    if a:
        if b:
            do()
        elif c:
            other()


# === nested-guard-invert: nested early-exit + sibling code ===


# CASE: invertible_return / fires nested-guard-invert
def case_invertible_return(a, b):
    if a:
        if b:
            return
        other()


# CASE: invertible_continue / fires nested-guard-invert
def case_invertible_continue(items, a):
    for x in items:
        if a:
            if cond(x):
                continue
            do(x)


# CASE: invertible_raise / fires nested-guard-invert
def case_invertible_raise(a, b):
    if a:
        if b:
            raise ValueError
        do()


# CASE: invertible_break / fires nested-guard-invert
def case_invertible_break(items, a):
    for _ in items:
        if a:
            if cond(_):
                break
            do(_)


# CASE: invertible_leading_stmt / fires nested-guard-invert
def case_invertible_leading_stmt(a, b):
    if a:
        do()
        if b:
            return


# === false positives for nested-guard-invert (must NOT fire) ===


# CASE: no_early_exit_with_sibling / negative
def case_no_early_exit_with_sibling(a, b):
    if a:
        if b:
            do()
        other()


# CASE: strict_no_sibling_with_exit / fires nested-if-no-else (strict shape;
# inner exit doesn't escalate it to invert because there's no sibling code)
def case_strict_no_sibling_with_exit(a, b):
    if a:
        if b:
            return


# CASE: inner_has_else_with_exit / negative
def case_inner_has_else_with_exit(a, b):
    if a:
        if b:
            return
        do()
        other()


# CASE: outer_not_tail_dispatch_shape / negative
# The nested early-exit branch is part of a type-dispatch chain, not a
# tail-position guard that can be cleanly inverted.
def case_outer_not_tail_dispatch_shape(kind, raw):
    if kind == "identifier":
        if raw is None:
            return
        do(raw)
    if kind == "literal":
        return
    other(kind)


# CASE: outer_has_else_with_exit_guard / negative
# Outer if has an else branch, so guard inversion is not a simple flatten.
def case_outer_has_else_with_exit_guard(a, b):
    if a:
        if b:
            return
        other()
    else:
        do()

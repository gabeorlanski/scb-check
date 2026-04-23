"""Fixture for init-populate-iterate-list rule.

Line numbers are asserted in tests/analysis/test_init_populate_iterate_list_rule.py.
"""

from __future__ import annotations


def sink(*_a):
    pass


# CASE: simple_consumer / fires init-populate-iterate-list
def case_simple_consumer(items):
    collected = []
    for item in items:
        collected.append(item)

    for value in collected:
        sink(value)


# CASE: multi_stmt_consumer / negative
# Multi-step consumption is intentionally explicit and should not be flagged.
def case_multi_stmt_consumer(items):
    collected = []
    for item in items:
        collected.append(item)

    for value in collected:
        processed = value.strip()
        sink(processed)


# CASE: nested_control_consumer / negative
def case_nested_control_consumer(items):
    collected = []
    for item in items:
        collected.append(item)

    for value in collected:
        if value:
            sink(value)

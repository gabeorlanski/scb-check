"""Fixture exercising every type-annotation slop rule plus known false-positive controls.

Line numbers are asserted in tests/analysis/test_type_annotation_rules.py — keep this
file in sync when adding or reordering cases.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from typing import (
    Any,
    AnyStr,
)


class MyAnyWrapper: ...


class MyType: ...


# --- generic-with-any ---
g_dict_upper: dict[str, Any]  # line 18
g_list_upper: list[Any]  # line 19
g_dict_lower: dict[str, Any]  # line 20
g_list_lower: list[Any]  # line 21
g_tuple: tuple[Any, ...]  # line 22
g_set: set[Any]  # line 23
g_mapping: Mapping[str, Any]  # line 24
g_sequence: Sequence[Any]  # line 25
g_dict_both: dict[Any, Any]  # line 26

# --- union-with-any ---
u_trailing: str | Any  # line 29
u_leading: Any | int  # line 30
u_pipe_trailing: str | Any  # line 31
u_pipe_leading: Any | int  # line 32
u_pipe_three: int | None | Any  # line 33

# --- optional-any ---
o_wrapped: Any | None  # line 36
o_pipe_trailing: Any | None  # line 37
o_pipe_leading: None | Any  # line 38

# --- callable-any-return ---
c_ellipsis: Callable[..., Any]  # line 41
c_typed_params: Callable[[int, str], Any]  # line 42

# --- object-type-annotation ---
obj_bare: object  # line 45
obj_string: object  # line 46
obj_qualified: builtins.object  # line 47

# --- FALSE POSITIVE CONTROLS (must NOT fire any type-annotation rule) ---
fp_anystr: str | AnyStr  # line 50 - AnyStr is a legitimate typing primitive
fp_userlike: MyAnyWrapper | int  # line 51 - substring "Any" in user type
fp_concrete_dict: dict[str, int]  # line 52
fp_concrete_list: list[str]  # line 53
fp_concrete_return: Callable[..., int]  # line 54
fp_any_param: Callable[
    [Any], int
]  # line 55 - Any input, concrete return is legit
fp_forward_ref: MyType  # line 56

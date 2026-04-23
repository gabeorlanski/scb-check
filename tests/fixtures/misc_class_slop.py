"""Fixture exercising misc.yaml class-shape rules. Line numbers are
asserted in tests/analysis/test_misc_class_rules.py - keep in sync when
editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# === empty-exception-subclass: FIRES ===


class FooError(Exception):
    pass


class BarError(Exception):
    """A docstring-only exception."""


class BazError(Exception):
    exit_code = 4
    error_type = "Baz"


class ChildError(FooError):
    pass


class MyWarning(Warning):
    pass


class QuxError(Exception):
    """Something."""

    exit_code = 1
    pass


# === empty-exception-subclass: MUST NOT FIRE ===


class RealError(Exception):
    def __init__(self, msg: str, code: int) -> None:
        super().__init__(msg)
        self.code = code


class AnotherError(Exception):
    @property
    def payload(self) -> dict[str, int]:
        return {"k": 1}


class JustAClass:
    pass


class NoBase:
    pass


# === dataclass-tagged-union-discriminator: FIRES ===


@dataclass
class ComposeSegment:
    kind: str
    ref: str | None = None
    steps: list[Any] | None = None
    params: dict[str, Any] | None = None


@dataclass
class Event:
    type: str
    payload: dict | None = None
    source: str | None = None


@dataclass(frozen=True)
class Message:
    tag: str
    body: bytes | None = None
    meta: dict | None = None


# === dataclass-tagged-union-discriminator: MUST NOT FIRE ===


@dataclass
class SingleOpt:
    kind: str
    payload: str | None = None


@dataclass
class Regular:
    name: str
    value: int | None = None
    extra: str | None = None


@dataclass
class NotFirst:
    id: int
    kind: str
    extra: str | None = None
    other: int | None = None


@dataclass
class Discriminated:
    kind: Literal[foo]
    a: str | None = None
    b: int | None = None


class PlainClass:
    kind: str
    a: str | None = None
    b: int | None = None

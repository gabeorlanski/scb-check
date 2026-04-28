"""Helpers for Python string literal analysis."""

from __future__ import annotations


def string_prefix(literal: str) -> str:
    """Return the lowercase prefix before a Python string literal quote."""
    prefix_chars: list[str] = []
    for character in literal:
        if character in {'"', "'"}:
            break
        prefix_chars.append(character.lower())
    return "".join(prefix_chars)

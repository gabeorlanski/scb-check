from __future__ import annotations

from typing import TYPE_CHECKING

from scb_check.analysis.loc import sloc_line_numbers

if TYPE_CHECKING:
    import pytest


def test_sloc_skips_blank_and_comments() -> None:
    """Blank lines and comments are excluded from SLOC."""
    source = """
# one
alpha = 1

# two
beta = 2  # inline comments still count
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({2, 5})


def test_sloc_skips_docstrings() -> None:
    """Module and function docstrings are excluded from SLOC."""
    source = '''
"""module docstring"""

def marker():
    """function docstring"""
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({3, 5})


def test_sloc_skips_standalone_strings() -> None:
    """Standalone string statements follow radon's non-SLOC behavior."""
    source = '''
def marker():
    value = 1
    """not a real docstring, but radon treats it as non-sloc"""
    return value
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 4})


def test_sloc_skips_multiline_docstrings() -> None:
    """Multiline docstring bodies are excluded from SLOC."""
    source = '''
def marker():
    """
    doc line

    more doc
    """
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 7})


def test_sloc_counts_f_strings() -> None:
    """F-string expression statements are counted as SLOC."""
    source = """
def marker():
    f"not a docstring"
    return 1
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 3})


def test_sloc_hides_escape_warnings(
    recwarn: pytest.WarningsRecorder,
) -> None:
    """Invalid escape sequences do not leak SyntaxWarning records."""
    source = """
def marker():
    pattern = "\\_"
    return pattern
""".strip("\n")

    sloc_line_numbers(source)

    syntax_warnings = [
        warning
        for warning in recwarn
        if issubclass(warning.category, SyntaxWarning)
        and "invalid escape sequence" in str(warning.message)
    ]
    assert syntax_warnings == []

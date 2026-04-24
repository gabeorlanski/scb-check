from __future__ import annotations

from scb_check.analysis.loc import sloc_line_numbers


def test_01() -> None:
    source = """
# one
alpha = 1

# two
beta = 2  # inline comments still count
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({2, 5})


def test_02() -> None:
    source = '''
"""module docstring"""

def marker():
    """function docstring"""
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({3, 5})


def test_03() -> None:
    source = '''
def marker():
    value = 1
    """not a real docstring, but radon treats it as non-sloc"""
    return value
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 4})


def test_04() -> None:
    source = '''
def marker():
    """
    doc line

    more doc
    """
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 7})


def test_05() -> None:
    source = """
def marker():
    f"not a docstring"
    return 1
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 3})


def test_06(
    recwarn,
) -> None:  # type: ignore[no-untyped-def]
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

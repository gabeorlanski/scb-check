from __future__ import annotations

from scb_check.analysis.loc import sloc_line_numbers


def test_sloc_line_numbers_tracks_1_indexed_lines() -> None:
    source = """
# one
alpha = 1

# two
beta = 2  # inline comments still count
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({2, 5})


def test_sloc_line_numbers_excludes_docstrings() -> None:
    source = '''
"""module docstring"""

def marker():
    """function docstring"""
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({3, 5})


def test_sloc_line_numbers_excludes_standalone_plain_strings() -> None:
    source = '''
def marker():
    value = 1
    """not a real docstring, but radon treats it as non-sloc"""
    return value
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 4})


def test_sloc_line_numbers_excludes_multiline_plain_strings() -> None:
    source = '''
def marker():
    """
    doc line

    more doc
    """
    return 1
'''.strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 7})


def test_sloc_line_numbers_keeps_f_string_expression() -> None:
    source = """
def marker():
    f"not a docstring"
    return 1
""".strip("\n")

    assert sloc_line_numbers(source) == frozenset({1, 2, 3})


def test_sloc_line_numbers_does_not_warn_for_invalid_escape_sequence(
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

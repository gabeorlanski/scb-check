"""JavaScript Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_javascript

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

_JAVASCRIPT_FUNCTIONS = frozenset(
    {
        "arrow_function",
        "function",
        "function_declaration",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    },
)
_JAVASCRIPT_ANONYMOUS_FUNCTIONS = frozenset(
    {"arrow_function", "function", "generator_function"},
)
_JAVASCRIPT_BRANCHES = frozenset(
    {"catch_clause", "if_statement", "switch_statement", "ternary_expression"},
)
_JAVASCRIPT_LOOPS = frozenset(
    {"do_statement", "for_in_statement", "for_statement", "while_statement"},
)
_JAVASCRIPT_LITERALS = frozenset(
    {
        "false",
        "null",
        "number",
        "regex",
        "string",
        "string_fragment",
        "template_string",
        "true",
        "undefined",
    },
)

JAVASCRIPT_CONFIG = TreeSitterLanguageConfig(
    language=Language.JAVASCRIPT,
    tree_sitter_language=tree_sitter_javascript.language,
    function_node_types=_JAVASCRIPT_FUNCTIONS,
    class_node_types=frozenset({"class_declaration"}),
    anonymous_function_node_types=_JAVASCRIPT_ANONYMOUS_FUNCTIONS,
    body_node_types=frozenset({"statement_block"}),
    branch_node_types=_JAVASCRIPT_BRANCHES,
    loop_node_types=_JAVASCRIPT_LOOPS,
    jump_node_types=frozenset({"break_statement", "continue_statement"}),
    boolean_expression_node_types=frozenset({"binary_expression"}),
    comment_node_types=frozenset({"comment"}),
    clone_node_types=_JAVASCRIPT_FUNCTIONS | _JAVASCRIPT_BRANCHES | _JAVASCRIPT_LOOPS,
    literal_node_types=_JAVASCRIPT_LITERALS,
)


class JavaScriptParser(GenericTreeSitterParser):
    """Parse JavaScript source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the JavaScript parser."""
        super().__init__(JAVASCRIPT_CONFIG)

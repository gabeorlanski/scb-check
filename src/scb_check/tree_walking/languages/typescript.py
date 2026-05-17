"""TypeScript Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_typescript

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

_TYPESCRIPT_FUNCTIONS = frozenset(
    {
        "arrow_function",
        "function",
        "function_declaration",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    },
)
_TYPESCRIPT_ANONYMOUS_FUNCTIONS = frozenset(
    {"arrow_function", "function", "generator_function"},
)
_TYPESCRIPT_BRANCHES = frozenset(
    {"catch_clause", "if_statement", "switch_statement", "ternary_expression"},
)
_TYPESCRIPT_LOOPS = frozenset(
    {"do_statement", "for_in_statement", "for_statement", "while_statement"},
)
_TYPESCRIPT_LITERALS = frozenset(
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

TYPESCRIPT_CONFIG = TreeSitterLanguageConfig(
    language=Language.TYPESCRIPT,
    tree_sitter_language=tree_sitter_typescript.language_typescript,
    function_node_types=_TYPESCRIPT_FUNCTIONS,
    class_node_types=frozenset({"class_declaration"}),
    anonymous_function_node_types=_TYPESCRIPT_ANONYMOUS_FUNCTIONS,
    body_node_types=frozenset({"statement_block"}),
    branch_node_types=_TYPESCRIPT_BRANCHES,
    loop_node_types=_TYPESCRIPT_LOOPS,
    jump_node_types=frozenset({"break_statement", "continue_statement"}),
    boolean_expression_node_types=frozenset({"binary_expression"}),
    comment_node_types=frozenset({"comment"}),
    clone_node_types=_TYPESCRIPT_FUNCTIONS | _TYPESCRIPT_BRANCHES | _TYPESCRIPT_LOOPS,
    literal_node_types=_TYPESCRIPT_LITERALS,
)


class TypeScriptParser(GenericTreeSitterParser):
    """Parse TypeScript source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the TypeScript parser."""
        super().__init__(TYPESCRIPT_CONFIG)

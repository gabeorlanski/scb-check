"""C++ Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_cpp

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

_CPP_BRANCHES = frozenset(
    {"catch_clause", "conditional_expression", "if_statement", "switch_statement"},
)
_CPP_LOOPS = frozenset(
    {"do_statement", "for_range_loop", "for_statement", "while_statement"},
)

CPP_CONFIG = TreeSitterLanguageConfig(
    language=Language.CPP,
    tree_sitter_language=tree_sitter_cpp.language,
    function_node_types=frozenset({"function_definition"}),
    class_node_types=frozenset({"class_specifier", "struct_specifier"}),
    body_node_types=frozenset({"compound_statement"}),
    branch_node_types=_CPP_BRANCHES,
    loop_node_types=_CPP_LOOPS,
    jump_node_types=frozenset({"break_statement", "continue_statement"}),
    boolean_expression_node_types=frozenset({"binary_expression"}),
    comment_node_types=frozenset({"comment"}),
    clone_node_types=frozenset({"function_definition"}) | _CPP_BRANCHES | _CPP_LOOPS,
    literal_node_types=frozenset(
        {
            "char_literal",
            "false",
            "float_literal",
            "null",
            "number_literal",
            "raw_string_literal",
            "string_content",
            "string_literal",
            "true",
        },
    ),
)


class CPPParser(GenericTreeSitterParser):
    """Parse C++ source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the C++ parser."""
        super().__init__(CPP_CONFIG)

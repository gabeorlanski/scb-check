"""Rust Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_rust

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

RUST_CONFIG = TreeSitterLanguageConfig(
    language=Language.RUST,
    tree_sitter_language=tree_sitter_rust.language,
    function_node_types=frozenset({"function_item"}),
    class_node_types=frozenset({"enum_item", "struct_item", "trait_item"}),
    owner_context_node_types=frozenset({"impl_item"}),
    body_node_types=frozenset({"block"}),
    branch_node_types=frozenset({"if_expression", "match_expression"}),
    loop_node_types=frozenset(
        {"for_expression", "loop_expression", "while_expression"},
    ),
    jump_node_types=frozenset({"break_expression", "continue_expression"}),
    boolean_expression_node_types=frozenset({"binary_expression"}),
    comment_node_types=frozenset({"block_comment", "line_comment"}),
    clone_node_types=frozenset(
        {
            "for_expression",
            "function_item",
            "if_expression",
            "loop_expression",
            "match_expression",
            "while_expression",
        },
    ),
    literal_node_types=frozenset(
        {
            "boolean_literal",
            "char_literal",
            "float_literal",
            "integer_literal",
            "raw_string_literal",
            "string_literal",
        },
    ),
)


class RustParser(GenericTreeSitterParser):
    """Parse Rust source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the Rust parser."""
        super().__init__(RUST_CONFIG)

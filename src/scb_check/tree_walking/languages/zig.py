"""Zig Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_zig

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

_ZIG_BRANCHES = frozenset({"if_statement", "switch_expression"})
_ZIG_LOOPS = frozenset({"for_statement", "while_statement"})

ZIG_CONFIG = TreeSitterLanguageConfig(
    language=Language.ZIG,
    tree_sitter_language=tree_sitter_zig.language,
    function_node_types=frozenset({"function_declaration"}),
    body_node_types=frozenset({"block"}),
    branch_node_types=_ZIG_BRANCHES,
    loop_node_types=_ZIG_LOOPS,
    jump_node_types=frozenset({"break_expression", "continue_expression"}),
    boolean_expression_node_types=frozenset({"binary_expression"}),
    comment_node_types=frozenset({"comment"}),
    clone_node_types=frozenset({"function_declaration"}) | _ZIG_BRANCHES | _ZIG_LOOPS,
    literal_node_types=frozenset(
        {
            "char_literal",
            "float",
            "integer",
            "string",
            "string_content",
        },
    ),
)


class ZigParser(GenericTreeSitterParser):
    """Parse Zig source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the Zig parser."""
        super().__init__(ZIG_CONFIG)

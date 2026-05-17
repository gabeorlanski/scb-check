"""Haskell Tree-sitter parser configuration."""

from __future__ import annotations

import tree_sitter_haskell

from scb_check.tree_walking.languages.generic import GenericTreeSitterParser
from scb_check.tree_walking.languages.generic import TreeSitterLanguageConfig
from scb_check.tree_walking.models import Language

_HASKELL_BRANCHES = frozenset({"case", "conditional", "guard"})
_HASKELL_LOOPS = frozenset[str]()

HASKELL_CONFIG = TreeSitterLanguageConfig(
    language=Language.HASKELL,
    tree_sitter_language=tree_sitter_haskell.language,
    function_node_types=frozenset({"function"}),
    body_node_types=frozenset({"match"}),
    branch_node_types=_HASKELL_BRANCHES,
    loop_node_types=_HASKELL_LOOPS,
    boolean_expression_node_types=frozenset({"infix"}),
    boolean_operator_tokens=frozenset({"&&", "||"}),
    comment_node_types=frozenset({"comment", "haddock"}),
    clone_node_types=frozenset({"function"}) | _HASKELL_BRANCHES,
    identifier_node_types=frozenset({"constructor", "module_id", "variable"}),
    literal_node_types=frozenset(
        {
            "char",
            "float",
            "integer",
            "literal",
            "string",
        },
    ),
)


class HaskellParser(GenericTreeSitterParser):
    """Parse Haskell source into minimal IR."""

    def __init__(self) -> None:
        """Initialize the Haskell parser."""
        super().__init__(HASKELL_CONFIG)

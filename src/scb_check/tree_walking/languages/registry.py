"""Language parser configuration registry."""

from __future__ import annotations

from scb_check.tree_walking.languages.cpp import CPP_CONFIG
from scb_check.tree_walking.languages.haskell import HASKELL_CONFIG
from scb_check.tree_walking.languages.javascript import JAVASCRIPT_CONFIG
from scb_check.tree_walking.languages.rust import RUST_CONFIG
from scb_check.tree_walking.languages.typescript import TYPESCRIPT_CONFIG
from scb_check.tree_walking.languages.zig import ZIG_CONFIG
from scb_check.tree_walking.models import Language

LANGUAGE_CONFIGS = {
    config.language: config
    for config in (
        CPP_CONFIG,
        HASKELL_CONFIG,
        JAVASCRIPT_CONFIG,
        RUST_CONFIG,
        TYPESCRIPT_CONFIG,
        ZIG_CONFIG,
    )
}


def clone_node_types_for_language(language: Language) -> frozenset[str]:
    """Return clone candidate node types for `language`."""
    config = LANGUAGE_CONFIGS.get(language)
    return config.clone_node_types if config is not None else frozenset()


def comment_node_types_for_language(language: Language) -> frozenset[str]:
    """Return comment node types for `language`."""
    config = LANGUAGE_CONFIGS.get(language)
    return config.comment_node_types if config is not None else frozenset({"comment"})


def identifier_node_types_for_language(language: Language) -> frozenset[str]:
    """Return identifier-like node types for `language`."""
    config = LANGUAGE_CONFIGS.get(language)
    return config.identifier_node_types if config is not None else frozenset()


def literal_node_types_for_language(language: Language) -> frozenset[str]:
    """Return literal node types for `language`."""
    config = LANGUAGE_CONFIGS.get(language)
    return config.literal_node_types if config is not None else frozenset()

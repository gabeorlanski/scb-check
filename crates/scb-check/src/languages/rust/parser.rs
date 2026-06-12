use std::collections::BTreeSet;

use tree_sitter::Node;

use crate::languages::{BaseParser, CommentSpan, FunctionSpan, LanguageParser};

pub(crate) static RUST_PARSER: RustLanguageParser = RustLanguageParser;

#[derive(Debug, Clone, Copy)]
pub(crate) struct RustLanguageParser;

impl LanguageParser for RustLanguageParser {
    fn label(&self) -> &'static str {
        "rust"
    }

    fn tree_sitter_language(&self) -> tree_sitter::Language {
        tree_sitter_rust::LANGUAGE.into()
    }

    fn is_function_node(&self, kind: &str) -> bool {
        kind == "function_item"
    }

    fn is_comment_node(&self, kind: &str) -> bool {
        matches!(kind, "line_comment" | "block_comment")
    }

    fn build_function(&self, source: &str, node: Node<'_>) -> FunctionSpan {
        BaseParser::function_span(
            source,
            node,
            1 + Self::cyclomatic_increment(node),
            node.children(&mut node.walk())
                .map(|child| Self::cognitive_for_node(child, 0))
                .sum(),
            Self::max_nesting_for_node(node),
        )
    }

    fn sloc_lines(
        &self,
        source: &str,
        _root: Node<'_>,
        comments: &[CommentSpan],
    ) -> BTreeSet<usize> {
        BaseParser::generic_sloc_lines(source, comments)
    }
}

impl RustLanguageParser {
    fn cyclomatic_increment(node: Node<'_>) -> usize {
        let mut total =
            usize::from(Self::is_complexity_node(node) || Self::is_boolean_operation(node));
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            total += Self::cyclomatic_increment(child);
        }
        total
    }

    fn cognitive_for_node(node: Node<'_>, nesting: usize) -> usize {
        if Self::is_boolean_operation(node) {
            return 1 + Self::child_cognitive_score(node, nesting);
        }
        if matches!(node.kind(), "break_expression" | "continue_expression") {
            return 1;
        }
        if Self::is_complexity_node(node) {
            return 1 + nesting + Self::child_cognitive_score(node, nesting + 1);
        }
        Self::child_cognitive_score(node, nesting)
    }

    fn child_cognitive_score(node: Node<'_>, nesting: usize) -> usize {
        node.children(&mut node.walk())
            .map(|child| Self::cognitive_for_node(child, nesting))
            .sum()
    }

    fn max_nesting_for_node(node: Node<'_>) -> usize {
        let mut max_nesting = 0;
        let mut stack = vec![(node, 0)];
        while let Some((current, nesting)) = stack.pop() {
            max_nesting = max_nesting.max(nesting);
            let child_nesting = if Self::is_complexity_node(current) {
                nesting + 1
            } else {
                nesting
            };
            let mut cursor = current.walk();
            stack.extend(
                current
                    .children(&mut cursor)
                    .map(|child| (child, child_nesting)),
            );
        }
        max_nesting
    }

    fn is_complexity_node(node: Node<'_>) -> bool {
        matches!(
            node.kind(),
            "if_expression"
                | "match_expression"
                | "for_expression"
                | "loop_expression"
                | "while_expression"
        )
    }

    fn is_boolean_operation(node: Node<'_>) -> bool {
        if node.kind() != "binary_expression" {
            return false;
        }
        let mut cursor = node.walk();
        node.children(&mut cursor)
            .any(|child| matches!(child.kind(), "&&" | "||"))
    }
}

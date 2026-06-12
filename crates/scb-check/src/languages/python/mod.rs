use std::collections::BTreeSet;

use tree_sitter::Node;

use crate::languages::{
    BaseParser, CommentSpan, FunctionSpan, LanguageParser, push_children_reverse, signature_params,
};
use crate::model::Language;

pub static PYTHON_PARSER: PythonLanguageParser = PythonLanguageParser;

#[derive(Debug, Clone, Copy)]
pub struct PythonLanguageParser;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SlocVisit {
    Record(usize),
    Descend,
    Skip,
}

impl LanguageParser for PythonLanguageParser {
    fn language(&self) -> Language {
        Language::Python
    }

    fn label(&self) -> &'static str {
        "python"
    }

    fn tree_sitter_language(&self) -> tree_sitter::Language {
        tree_sitter_python::LANGUAGE.into()
    }

    fn is_function_node(&self, kind: &str) -> bool {
        kind == "function_definition"
    }

    fn is_comment_node(&self, kind: &str) -> bool {
        kind == "comment"
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
        root: Node<'_>,
        _comments: &[CommentSpan],
    ) -> BTreeSet<usize> {
        Self::python_sloc_lines(source, root)
    }

    fn function_params(&self, signature: &str) -> Vec<String> {
        signature_params(signature, Self::param_name)
    }

    fn function_body_lines<'source>(
        &self,
        lines: &'source [&'source str],
    ) -> &'source [&'source str] {
        Self::body_lines(lines)
    }

    fn function_body_statements<'source>(&self, lines: &'source [&str]) -> Vec<&'source str> {
        lines
            .iter()
            .map(|line| line.trim())
            .filter(|line| !line.is_empty())
            .filter(|line| !line.starts_with('#'))
            .collect()
    }

    fn call_keywords(&self) -> &'static [&'static str] {
        &Self::CALL_KEYWORDS
    }

    fn directive_text<'comment>(&self, comment: &'comment CommentSpan) -> Option<&'comment str> {
        comment.text.strip_prefix('#').map(str::trim)
    }
}

impl PythonLanguageParser {
    const CALL_KEYWORDS: [&'static str; 14] = [
        "if", "elif", "for", "while", "return", "raise", "with", "def", "class", "lambda", "not",
        "and", "or", "assert",
    ];

    fn param_name(param: &str) -> Option<String> {
        let name = param.split([':', '=']).next().unwrap_or_default().trim();
        (!name.is_empty() && name != "self" && name != "cls").then(|| name.to_string())
    }

    fn body_lines<'line>(lines: &'line [&str]) -> &'line [&'line str] {
        if lines.len() <= 1 { &[] } else { &lines[1..] }
    }

    fn python_sloc_lines(source: &str, root: Node<'_>) -> BTreeSet<usize> {
        let mut lines = BTreeSet::new();
        Self::collect_python_sloc_token_lines(source, root, &mut lines);
        let source_lines: Vec<&str> = source.lines().collect();
        for (start, end) in Self::plain_string_ranges(source, root, &source_lines) {
            for line in start..=end {
                lines.remove(&line);
            }
        }
        lines
    }

    fn collect_python_sloc_token_lines(source: &str, node: Node<'_>, lines: &mut BTreeSet<usize>) {
        let mut stack = vec![node];
        while let Some(current) = stack.pop() {
            match Self::classify_sloc_visit(source, current) {
                SlocVisit::Record(line) => {
                    lines.insert(line);
                }
                SlocVisit::Descend => push_children_reverse(current, &mut stack),
                SlocVisit::Skip => {}
            }
        }
    }

    fn classify_sloc_visit(source: &str, node: Node<'_>) -> SlocVisit {
        if node.kind() == "comment" {
            return SlocVisit::Skip;
        }
        if BaseParser::is_string_node(node.kind()) {
            return SlocVisit::Record(node.start_position().row + 1);
        }
        if node.child_count() != 0 {
            return SlocVisit::Descend;
        }

        let text = node.utf8_text(source.as_bytes()).unwrap_or_default().trim();
        if text.is_empty() {
            SlocVisit::Skip
        } else {
            SlocVisit::Record(node.start_position().row + 1)
        }
    }

    fn plain_string_ranges(
        source: &str,
        root: Node<'_>,
        source_lines: &[&str],
    ) -> Vec<(usize, usize)> {
        let mut ranges = Vec::new();
        let mut stack = vec![root];
        while let Some(node) = stack.pop() {
            if let Some(literal) = Self::owned_plain_string_literal(source, node, source_lines) {
                ranges.push((
                    literal.start_position().row + 1,
                    literal.end_position().row + 1,
                ));
            }
            let mut cursor = node.walk();
            stack.extend(node.named_children(&mut cursor));
        }
        ranges
    }

    fn owned_plain_string_literal<'tree>(
        source: &str,
        node: Node<'tree>,
        source_lines: &[&str],
    ) -> Option<Node<'tree>> {
        if node.kind() != "expression_statement" || node.named_child_count() != 1 {
            return None;
        }
        let literal = node.named_child(0)?;
        ((BaseParser::is_string_node(literal.kind())
            || BaseParser::is_string_statement_text(source, literal))
            && Self::owns_line(literal, source_lines))
        .then_some(literal)
    }

    fn owns_line(literal: Node<'_>, source_lines: &[&str]) -> bool {
        let start = literal.start_position();
        let end = literal.end_position();
        let start_line = source_lines.get(start.row).copied().unwrap_or_default();
        let end_line = source_lines.get(end.row).copied().unwrap_or_default();
        start_line
            .get(..start.column)
            .unwrap_or_default()
            .trim()
            .is_empty()
            && end_line
                .get(end.column..)
                .unwrap_or_default()
                .trim()
                .is_empty()
    }

    fn cyclomatic_increment(node: Node<'_>) -> usize {
        let mut total = usize::from(Self::is_cyclomatic_node(node.kind()));
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            total += Self::cyclomatic_increment(child);
        }
        total
    }

    fn cognitive_for_node(node: Node<'_>, nesting: usize) -> usize {
        if node.kind() == "boolean_operator" {
            return 1 + Self::child_cognitive_score(node, nesting);
        }
        if matches!(node.kind(), "break_statement" | "continue_statement") {
            return 1;
        }
        if Self::is_cognitive_flow_break_node(node.kind()) {
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
            let child_nesting = if Self::is_cognitive_flow_break_node(current.kind()) {
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

    fn is_cognitive_flow_break_node(kind: &str) -> bool {
        matches!(
            kind,
            "if_statement"
                | "elif_clause"
                | "else_clause"
                | "for_statement"
                | "while_statement"
                | "except_clause"
                | "conditional_expression"
        )
    }

    fn is_cyclomatic_node(kind: &str) -> bool {
        matches!(
            kind,
            "if_statement"
                | "elif_clause"
                | "for_statement"
                | "while_statement"
                | "except_clause"
                | "assert_statement"
                | "list_comprehension"
                | "set_comprehension"
                | "dictionary_comprehension"
                | "generator_expression"
                | "boolean_operator"
                | "conditional_expression"
                | "if_clause"
        )
    }
}

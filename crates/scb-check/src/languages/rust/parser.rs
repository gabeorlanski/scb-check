use tree_sitter::Node;

use crate::languages::base::{
    ParsedSyntax, collect_comments, collect_functions, count_nodes, function_span,
    generic_sloc_lines, parse_tree,
};

pub(crate) fn parse_syntax(source: &str) -> Result<ParsedSyntax, String> {
    let language = tree_sitter_rust::LANGUAGE.into();
    let tree = parse_tree(&language, "rust", source)?;
    let root = tree.root_node();
    let mut functions = Vec::new();
    collect_functions(source, root, &mut functions, is_function, build_function);
    let mut comments = Vec::new();
    collect_comments(source, root, &mut comments, is_comment);
    let sloc_lines = generic_sloc_lines(source, &comments);
    Ok(ParsedSyntax {
        functions,
        comments,
        sloc_lines,
        node_count: count_nodes(root),
    })
}

fn is_function(kind: &str) -> bool {
    kind == "function_item"
}

fn build_function(source: &str, node: Node<'_>) -> crate::languages::FunctionSpan {
    function_span(
        source,
        node,
        1 + cyclomatic_increment(node),
        node.children(&mut node.walk())
            .map(|child| cognitive_for_node(child, 0))
            .sum(),
        max_nesting_for_node(node),
    )
}

fn is_comment(kind: &str) -> bool {
    matches!(kind, "line_comment" | "block_comment")
}

fn cyclomatic_increment(node: Node<'_>) -> usize {
    let mut total = usize::from(is_complexity_node(node) || is_boolean_operation(node));
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        total += cyclomatic_increment(child);
    }
    total
}

fn cognitive_for_node(node: Node<'_>, nesting: usize) -> usize {
    let child_score: usize = node
        .children(&mut node.walk())
        .map(|child| cognitive_for_node(child, nesting))
        .sum();
    if is_boolean_operation(node) {
        return 1 + child_score;
    }
    if matches!(node.kind(), "break_expression" | "continue_expression") {
        return 1;
    }
    if is_complexity_node(node) {
        let nested_score: usize = node
            .children(&mut node.walk())
            .map(|child| cognitive_for_node(child, nesting + 1))
            .sum();
        return 1 + nesting + nested_score;
    }
    child_score
}

fn max_nesting_for_node(node: Node<'_>) -> usize {
    let mut max_nesting = 0;
    let mut stack = vec![(node, 0)];
    while let Some((current, nesting)) = stack.pop() {
        max_nesting = max_nesting.max(nesting);
        let child_nesting = if is_complexity_node(current) {
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

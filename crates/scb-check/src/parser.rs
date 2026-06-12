use std::collections::{BTreeMap, BTreeSet, HashMap};

use tree_sitter::{Node, Parser};

use crate::model::Language;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CommentSpan {
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct FunctionSpan {
    pub name: String,
    pub start_line: usize,
    pub end_line: usize,
    pub signature: String,
    pub cyclomatic: usize,
    pub cognitive: usize,
    pub max_nesting: usize,
    pub clone_fingerprint: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ParsedSyntax {
    pub functions: Vec<FunctionSpan>,
    pub comments: Vec<CommentSpan>,
    pub sloc_lines: BTreeSet<usize>,
    pub node_count: usize,
}

pub(crate) fn parse_syntax(language: Language, source: &str) -> Result<ParsedSyntax, String> {
    let mut parser = Parser::new();
    let tree_sitter_language = match language {
        Language::Python => tree_sitter_python::LANGUAGE.into(),
        Language::Rust => tree_sitter_rust::LANGUAGE.into(),
    };
    parser
        .set_language(&tree_sitter_language)
        .map_err(|error| format!("failed to load {} parser: {error}", language.as_str()))?;
    let tree = parser
        .parse(source, None)
        .ok_or_else(|| format!("failed to parse {} source", language.as_str()))?;
    let root = tree.root_node();
    let mut functions = Vec::new();
    collect_functions(language, source, root, &mut functions);
    let mut comments = Vec::new();
    collect_comments(language, source, root, &mut comments);
    let sloc_lines = sloc_lines(language, source, root, &comments);
    Ok(ParsedSyntax {
        functions,
        comments,
        sloc_lines,
        node_count: count_nodes(root),
    })
}

fn collect_functions(
    language: Language,
    source: &str,
    node: Node<'_>,
    functions: &mut Vec<FunctionSpan>,
) {
    if is_function_node(language, node) {
        functions.push(function_span(language, source, node));
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_functions(language, source, child, functions);
    }
}

fn is_function_node(language: Language, node: Node<'_>) -> bool {
    let kind = node.kind();
    match language {
        Language::Python => kind == "function_definition",
        Language::Rust => kind == "function_item",
    }
}

fn collect_comments(
    language: Language,
    source: &str,
    node: Node<'_>,
    comments: &mut Vec<CommentSpan>,
) {
    if is_comment_node(language, node.kind()) {
        comments.push(CommentSpan {
            line: node.start_position().row + 1,
            column: node.start_position().column,
            end_line: node.end_position().row + 1,
            end_column: node.end_position().column,
            text: node
                .utf8_text(source.as_bytes())
                .unwrap_or_default()
                .to_string(),
        });
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_comments(language, source, child, comments);
    }
}

fn is_comment_node(language: Language, kind: &str) -> bool {
    match language {
        Language::Python => kind == "comment",
        Language::Rust => matches!(kind, "line_comment" | "block_comment"),
    }
}

fn sloc_lines(
    language: Language,
    source: &str,
    root: Node<'_>,
    comments: &[CommentSpan],
) -> BTreeSet<usize> {
    match language {
        Language::Python => python_sloc_lines(source, root),
        Language::Rust => generic_sloc_lines(source, comments),
    }
}

fn python_sloc_lines(source: &str, root: Node<'_>) -> BTreeSet<usize> {
    let mut lines = BTreeSet::new();
    collect_python_sloc_token_lines(source, root, &mut lines);
    let source_lines: Vec<&str> = source.lines().collect();
    for (start, end) in plain_string_ranges(source, root, &source_lines) {
        for line in start..=end {
            lines.remove(&line);
        }
    }
    lines
}

fn collect_python_sloc_token_lines(source: &str, node: Node<'_>, lines: &mut BTreeSet<usize>) {
    if node.kind() == "comment" {
        return;
    }
    if is_string_node(node.kind()) {
        lines.insert(node.start_position().row + 1);
        return;
    }
    if node.child_count() == 0 {
        if !node
            .utf8_text(source.as_bytes())
            .unwrap_or_default()
            .trim()
            .is_empty()
        {
            lines.insert(node.start_position().row + 1);
        }
        return;
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_python_sloc_token_lines(source, child, lines);
    }
}

fn plain_string_ranges(source: &str, root: Node<'_>, source_lines: &[&str]) -> Vec<(usize, usize)> {
    let mut ranges = Vec::new();
    let mut stack = vec![root];
    while let Some(node) = stack.pop() {
        if let Some(literal) = owned_plain_string_literal(source, node, source_lines) {
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
    ((is_string_node(literal.kind()) || is_string_statement_text(source, literal))
        && owns_line(literal, source_lines))
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

fn generic_sloc_lines(source: &str, comments: &[CommentSpan]) -> BTreeSet<usize> {
    let source_lines: Vec<&str> = source.lines().collect();
    let comment_intervals = comment_intervals_by_line(comments);
    source_lines
        .iter()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_no = index + 1;
            let intervals = comment_intervals
                .get(&line_no)
                .map(Vec::as_slice)
                .unwrap_or_default();
            let uncommented = remove_intervals(line, intervals);
            (!uncommented.trim().is_empty() && !is_punctuation_only(&uncommented))
                .then_some(line_no)
        })
        .collect()
}

fn comment_intervals_by_line(comments: &[CommentSpan]) -> BTreeMap<usize, Vec<(usize, usize)>> {
    let mut intervals: BTreeMap<usize, Vec<(usize, usize)>> = BTreeMap::new();
    for comment in comments {
        for line_no in comment.line..=comment.end_line {
            let start = if line_no == comment.line {
                comment.column
            } else {
                0
            };
            let end = if line_no == comment.end_line {
                comment.end_column
            } else {
                usize::MAX
            };
            intervals.entry(line_no).or_default().push((start, end));
        }
    }
    for line_intervals in intervals.values_mut() {
        line_intervals.sort_unstable();
    }
    intervals
}

fn remove_intervals(line: &str, intervals: &[(usize, usize)]) -> String {
    if intervals.is_empty() {
        return line.to_string();
    }
    let mut parts = Vec::new();
    let mut cursor = 0;
    for (start, end) in intervals {
        let bounded_start = (*start).min(line.len());
        let bounded_end = (*end).min(line.len()).max(bounded_start);
        parts.push(&line[cursor..bounded_start]);
        cursor = cursor.max(bounded_end);
    }
    parts.push(&line[cursor..]);
    parts.join("")
}

fn is_punctuation_only(line: &str) -> bool {
    let stripped = line.trim();
    !stripped.is_empty()
        && stripped.chars().all(|character| {
            matches!(
                character,
                '{' | '}' | '[' | ']' | '(' | ')' | ';' | ',' | ':'
            )
        })
}

fn function_span(language: Language, source: &str, node: Node<'_>) -> FunctionSpan {
    let name = node
        .child_by_field_name("name")
        .and_then(|name| name.utf8_text(source.as_bytes()).ok())
        .unwrap_or("<unknown>")
        .to_string();
    let body = node.child_by_field_name("body");
    let start_line = node.start_position().row + 1;
    let end_line = node.end_position().row + 1;
    FunctionSpan {
        name,
        start_line,
        end_line,
        signature: signature_text(source, node),
        cyclomatic: 1 + cyclomatic_increment(language, node),
        cognitive: node
            .children(&mut node.walk())
            .map(|child| cognitive_for_node(language, child, 0))
            .sum(),
        max_nesting: max_nesting_for_node(language, node),
        clone_fingerprint: body
            .map(|body| clone_fingerprint(source, body))
            .unwrap_or_default(),
    }
}

fn signature_text(source: &str, node: Node<'_>) -> String {
    let Some(body) = node.child_by_field_name("body") else {
        return node
            .utf8_text(source.as_bytes())
            .unwrap_or_default()
            .to_string();
    };
    source[node.start_byte()..body.start_byte()]
        .trim()
        .trim_end_matches('{')
        .trim()
        .to_string()
}

fn count_nodes(node: Node<'_>) -> usize {
    let mut total = 1;
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        total += count_nodes(child);
    }
    total
}

fn clone_fingerprint(source: &str, body: Node<'_>) -> Vec<String> {
    let mut names = HashMap::new();
    let mut cursor = body.walk();
    body.children(&mut cursor)
        .filter_map(|child| clone_statement_fingerprint(source, child, &mut names))
        .collect()
}

fn clone_statement_fingerprint(
    source: &str,
    node: Node<'_>,
    names: &mut HashMap<String, String>,
) -> Option<String> {
    if is_clone_noise_node(source, node) {
        return None;
    }
    let mut tokens = Vec::new();
    collect_clone_tokens(source, node, names, &mut tokens);
    (!tokens.is_empty()).then(|| tokens.join(""))
}

fn collect_clone_tokens(
    source: &str,
    node: Node<'_>,
    names: &mut HashMap<String, String>,
    tokens: &mut Vec<String>,
) {
    if is_clone_noise_node(source, node) {
        return;
    }
    if let Some(token) = clone_leaf_token(source, node, names) {
        tokens.push(token);
        return;
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_clone_tokens(source, child, names, tokens);
    }
}

fn clone_leaf_token(
    source: &str,
    node: Node<'_>,
    names: &mut HashMap<String, String>,
) -> Option<String> {
    let kind = node.kind();
    if is_string_node(kind) {
        return Some("$STR".to_string());
    }
    if is_literal_node(kind) {
        return Some("$LIT".to_string());
    }
    if is_identifier_node(kind) {
        let token = node.utf8_text(source.as_bytes()).unwrap_or_default();
        return Some(normalize_identifier(token, names));
    }
    if node.child_count() != 0 {
        return None;
    }

    let token = node.utf8_text(source.as_bytes()).unwrap_or_default().trim();
    (!token.is_empty() && !is_clone_noise_token(token)).then(|| token.to_string())
}

fn is_clone_noise_node(source: &str, node: Node<'_>) -> bool {
    node.kind() == "comment" || is_plain_string_statement(source, node)
}

fn is_plain_string_statement(source: &str, node: Node<'_>) -> bool {
    if node.kind() != "expression_statement" || node.named_child_count() != 1 {
        return false;
    }
    node.named_child(0).is_some_and(|child| {
        is_string_node(child.kind()) || is_string_statement_text(source, child)
    })
}

fn is_string_statement_text(source: &str, node: Node<'_>) -> bool {
    let text = node.utf8_text(source.as_bytes()).unwrap_or_default().trim();
    (text.starts_with("\"\"\"") && text.ends_with("\"\"\""))
        || (text.starts_with("'''") && text.ends_with("'''"))
}

fn is_string_node(kind: &str) -> bool {
    matches!(
        kind,
        "string" | "string_literal" | "raw_string_literal" | "interpreted_string_literal"
    )
}

fn is_literal_node(kind: &str) -> bool {
    matches!(
        kind,
        "integer"
            | "float"
            | "true"
            | "false"
            | "none"
            | "integer_literal"
            | "float_literal"
            | "char_literal"
            | "boolean_literal"
    )
}

fn is_identifier_node(kind: &str) -> bool {
    matches!(
        kind,
        "identifier" | "field_identifier" | "shorthand_field_identifier"
    )
}

fn is_clone_noise_token(token: &str) -> bool {
    matches!(token, "{" | "}" | ":" | ";" | "," | "(" | ")" | "[" | "]")
}

fn normalize_identifier(token: &str, names: &mut HashMap<String, String>) -> String {
    let next_index = names.len() + 1;
    names
        .entry(token.to_string())
        .or_insert_with(|| format!("$VAR{next_index}"))
        .clone()
}

fn cyclomatic_increment(language: Language, node: Node<'_>) -> usize {
    let mut total = usize::from(is_complexity_node(language, node));
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        total += cyclomatic_increment(language, child);
    }
    total
}

fn cognitive_for_node(language: Language, node: Node<'_>, nesting: usize) -> usize {
    let child_score: usize = node
        .children(&mut node.walk())
        .map(|child| cognitive_for_node(language, child, nesting))
        .sum();
    if is_boolean_node(language, node) {
        return 1 + child_score;
    }
    if is_jump_node(language, node) {
        return 1;
    }
    if is_cognitive_flow_break_node(language, node) {
        let nested_score: usize = node
            .children(&mut node.walk())
            .map(|child| cognitive_for_node(language, child, nesting + 1))
            .sum();
        return 1 + nesting + nested_score;
    }
    child_score
}

fn max_nesting_for_node(language: Language, node: Node<'_>) -> usize {
    let mut max_nesting = 0;
    let mut stack = vec![(node, 0)];
    while let Some((current, nesting)) = stack.pop() {
        max_nesting = max_nesting.max(nesting);
        let child_nesting = if is_cognitive_flow_break_node(language, current) {
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

fn is_complexity_node(language: Language, node: Node<'_>) -> bool {
    match language {
        Language::Python => is_python_cyclomatic_node(node.kind()),
        Language::Rust => is_rust_complexity_node(node.kind()) || is_rust_boolean_operation(node),
    }
}

fn is_cognitive_flow_break_node(language: Language, node: Node<'_>) -> bool {
    match language {
        Language::Python => matches!(
            node.kind(),
            "if_statement"
                | "elif_clause"
                | "else_clause"
                | "for_statement"
                | "while_statement"
                | "except_clause"
                | "conditional_expression"
        ),
        Language::Rust => is_rust_complexity_node(node.kind()),
    }
}

fn is_boolean_node(language: Language, node: Node<'_>) -> bool {
    match language {
        Language::Python => node.kind() == "boolean_operator",
        Language::Rust => is_rust_boolean_operation(node),
    }
}

fn is_jump_node(language: Language, node: Node<'_>) -> bool {
    match language {
        Language::Python => matches!(node.kind(), "break_statement" | "continue_statement"),
        Language::Rust => matches!(node.kind(), "break_expression" | "continue_expression"),
    }
}

fn is_python_cyclomatic_node(kind: &str) -> bool {
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

fn is_rust_complexity_node(kind: &str) -> bool {
    matches!(
        kind,
        "if_expression"
            | "match_expression"
            | "for_expression"
            | "loop_expression"
            | "while_expression"
    )
}

fn is_rust_boolean_operation(node: Node<'_>) -> bool {
    if node.kind() != "binary_expression" {
        return false;
    }
    let mut cursor = node.walk();
    node.children(&mut cursor)
        .any(|child| matches!(child.kind(), "&&" | "||"))
}

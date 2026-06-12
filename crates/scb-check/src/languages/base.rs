use std::collections::{BTreeMap, BTreeSet, HashMap};

use tree_sitter::{Node, Tree};

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

pub(crate) fn parse_tree(
    language: &tree_sitter::Language,
    label: &str,
    source: &str,
) -> Result<Tree, String> {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(language)
        .map_err(|error| format!("failed to load {label} parser: {error}"))?;
    parser
        .parse(source, None)
        .ok_or_else(|| format!("failed to parse {label} source"))
}

pub(crate) fn collect_comments(
    source: &str,
    node: Node<'_>,
    comments: &mut Vec<CommentSpan>,
    is_comment: fn(&str) -> bool,
) {
    if is_comment(node.kind()) {
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
        collect_comments(source, child, comments, is_comment);
    }
}

pub(crate) fn collect_functions(
    source: &str,
    node: Node<'_>,
    functions: &mut Vec<FunctionSpan>,
    is_function: fn(&str) -> bool,
    build_function: fn(&str, Node<'_>) -> FunctionSpan,
) {
    if is_function(node.kind()) {
        functions.push(build_function(source, node));
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_functions(source, child, functions, is_function, build_function);
    }
}

pub(crate) fn function_span(
    source: &str,
    node: Node<'_>,
    cyclomatic: usize,
    cognitive: usize,
    max_nesting: usize,
) -> FunctionSpan {
    let name = node
        .child_by_field_name("name")
        .and_then(|name| name.utf8_text(source.as_bytes()).ok())
        .unwrap_or("<unknown>")
        .to_string();
    let body = node.child_by_field_name("body");
    FunctionSpan {
        name,
        start_line: node.start_position().row + 1,
        end_line: node.end_position().row + 1,
        signature: signature_text(source, node),
        cyclomatic,
        cognitive,
        max_nesting,
        clone_fingerprint: body
            .map(|body| clone_fingerprint(source, body))
            .unwrap_or_default(),
    }
}

pub(crate) fn signature_text(source: &str, node: Node<'_>) -> String {
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

pub(crate) fn count_nodes(node: Node<'_>) -> usize {
    let mut total = 1;
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        total += count_nodes(child);
    }
    total
}

pub(crate) fn generic_sloc_lines(source: &str, comments: &[CommentSpan]) -> BTreeSet<usize> {
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

pub(crate) fn is_string_node(kind: &str) -> bool {
    matches!(
        kind,
        "string" | "string_literal" | "raw_string_literal" | "interpreted_string_literal"
    )
}

pub(crate) fn is_string_statement_text(source: &str, node: Node<'_>) -> bool {
    let text = node.utf8_text(source.as_bytes()).unwrap_or_default().trim();
    (text.starts_with("\"\"\"") && text.ends_with("\"\"\""))
        || (text.starts_with("'''") && text.ends_with("'''"))
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

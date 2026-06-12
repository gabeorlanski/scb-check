use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;

use tree_sitter::{Node, Tree};

use crate::model::{BodyShape, CallSite, Function, Language};

mod python;
mod rust;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommentSpan {
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FunctionSpan {
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
pub struct ParsedSyntax {
    pub functions: Vec<FunctionSpan>,
    pub comments: Vec<CommentSpan>,
    pub sloc_lines: BTreeSet<usize>,
    pub node_count: usize,
}

pub trait LanguageParser {
    fn language(&self) -> Language;
    fn label(&self) -> &'static str;
    fn tree_sitter_language(&self) -> tree_sitter::Language;
    fn is_function_node(&self, kind: &str) -> bool;
    fn is_comment_node(&self, kind: &str) -> bool;
    fn build_function(&self, source: &str, node: Node<'_>) -> FunctionSpan;
    fn sloc_lines(&self, source: &str, root: Node<'_>, comments: &[CommentSpan])
    -> BTreeSet<usize>;
    fn function_params(&self, signature: &str) -> Vec<String>;
    fn function_body_lines<'source>(
        &self,
        lines: &'source [&'source str],
    ) -> &'source [&'source str];
    fn function_body_statements<'source>(&self, lines: &'source [&str]) -> Vec<&'source str>;
    fn call_keywords(&self) -> &'static [&'static str];
    fn lower_function(
        &self,
        path: &Path,
        span: &FunctionSpan,
        all_lines: &[&str],
        sloc_lines: &BTreeSet<usize>,
    ) -> Function {
        let lines = function_lines(span, all_lines);
        let body_lines = self.function_body_lines(lines);
        lower_function_from_parts(
            path,
            self.language(),
            span,
            sloc_lines,
            LoweredFunctionParts {
                params: self.function_params(&span.signature),
                body_lines,
                body_statements: self.function_body_statements(body_lines),
                call_keywords: self.call_keywords(),
            },
        )
    }
    fn directive_text<'comment>(&self, comment: &'comment CommentSpan) -> Option<&'comment str>;

    fn parse(&self, source: &str) -> Result<ParsedSyntax, String>
    where
        Self: Sized,
    {
        BaseParser::new(self.label(), self.tree_sitter_language()).parse(self, source)
    }
}

#[derive(Debug, Clone)]
pub struct BaseParser {
    label: &'static str,
    language: tree_sitter::Language,
}

impl BaseParser {
    const fn new(label: &'static str, language: tree_sitter::Language) -> Self {
        Self { label, language }
    }

    fn parse<P: LanguageParser>(
        &self,
        language_parser: &P,
        source: &str,
    ) -> Result<ParsedSyntax, String> {
        let tree = self.parse_tree(source)?;
        let root = tree.root_node();
        if root.has_error() {
            return Err(format!("failed to parse {} source", self.label));
        }
        let functions = Self::collect_functions(language_parser, source, root);
        let comments = Self::collect_comments(language_parser, source, root);
        let sloc_lines = language_parser.sloc_lines(source, root, &comments);
        Ok(ParsedSyntax {
            functions,
            comments,
            sloc_lines,
            node_count: Self::count_nodes(root),
        })
    }

    fn parse_tree(&self, source: &str) -> Result<Tree, String> {
        let mut parser = tree_sitter::Parser::new();
        parser
            .set_language(&self.language)
            .map_err(|error| format!("failed to load {} parser: {error}", self.label))?;
        parser
            .parse(source, None)
            .ok_or_else(|| format!("failed to parse {} source", self.label))
    }

    fn collect_functions<P: LanguageParser>(
        language_parser: &P,
        source: &str,
        root: Node<'_>,
    ) -> Vec<FunctionSpan> {
        Self::collect_nodes(root, |node| {
            language_parser
                .is_function_node(node.kind())
                .then(|| language_parser.build_function(source, node))
        })
    }

    fn collect_comments<P: LanguageParser>(
        language_parser: &P,
        source: &str,
        root: Node<'_>,
    ) -> Vec<CommentSpan> {
        Self::collect_nodes(root, |node| {
            language_parser
                .is_comment_node(node.kind())
                .then(|| CommentSpan {
                    line: node.start_position().row + 1,
                    column: node.start_position().column,
                    end_line: node.end_position().row + 1,
                    end_column: node.end_position().column,
                    text: node
                        .utf8_text(source.as_bytes())
                        .unwrap_or_default()
                        .to_string(),
                })
        })
    }

    fn collect_nodes<T>(root: Node<'_>, mut collect: impl FnMut(Node<'_>) -> Option<T>) -> Vec<T> {
        let mut items = Vec::new();
        let mut stack = vec![root];
        while let Some(node) = stack.pop() {
            if let Some(item) = collect(node) {
                items.push(item);
            }
            push_children_reverse(node, &mut stack);
        }
        items
    }

    fn count_nodes(root: Node<'_>) -> usize {
        let mut total = 0;
        let mut stack = vec![root];
        while let Some(node) = stack.pop() {
            total += 1;
            let mut cursor = node.walk();
            stack.extend(node.children(&mut cursor));
        }
        total
    }
}

impl BaseParser {
    pub fn function_span(
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
            signature: Self::signature_text(source, node),
            cyclomatic,
            cognitive,
            max_nesting,
            clone_fingerprint: body
                .map(|body| Self::clone_fingerprint(source, body))
                .unwrap_or_default(),
        }
    }

    pub fn generic_sloc_lines(source: &str, comments: &[CommentSpan]) -> BTreeSet<usize> {
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

    pub fn is_string_node(kind: &str) -> bool {
        matches!(
            kind,
            "string" | "string_literal" | "raw_string_literal" | "interpreted_string_literal"
        )
    }

    pub fn is_string_statement_text(source: &str, node: Node<'_>) -> bool {
        let text = node.utf8_text(source.as_bytes()).unwrap_or_default().trim();
        (text.starts_with("\"\"\"") && text.ends_with("\"\"\""))
            || (text.starts_with("'''") && text.ends_with("'''"))
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

    fn clone_fingerprint(source: &str, body: Node<'_>) -> Vec<String> {
        let mut names = HashMap::new();
        let mut cursor = body.walk();
        body.children(&mut cursor)
            .filter_map(|child| clone_statement_fingerprint(source, child, &mut names))
            .collect()
    }
}

pub fn parse_syntax(language: Language, source: &str) -> Result<ParsedSyntax, String> {
    match language {
        Language::Python => python::PYTHON_PARSER.parse(source),
        Language::Rust => rust::RUST_PARSER.parse(source),
    }
}

pub fn lower_function(
    language: Language,
    path: &Path,
    span: &FunctionSpan,
    all_lines: &[&str],
    sloc_lines: &BTreeSet<usize>,
) -> Function {
    match language {
        Language::Python => python::PYTHON_PARSER.lower_function(path, span, all_lines, sloc_lines),
        Language::Rust => rust::RUST_PARSER.lower_function(path, span, all_lines, sloc_lines),
    }
}

pub fn directive_text(language: Language, comment: &CommentSpan) -> Option<&str> {
    match language {
        Language::Python => python::PYTHON_PARSER.directive_text(comment),
        Language::Rust => rust::RUST_PARSER.directive_text(comment),
    }
}

pub fn function_lines<'source>(
    span: &FunctionSpan,
    all_lines: &'source [&'source str],
) -> &'source [&'source str] {
    if all_lines.is_empty() {
        return &[];
    }
    let start_index = span.start_line.saturating_sub(1).min(all_lines.len() - 1);
    let end_index = span.end_line.saturating_sub(1).min(all_lines.len() - 1);
    &all_lines[start_index..=end_index.max(start_index)]
}

fn lower_function_from_parts(
    path: &Path,
    language: Language,
    span: &FunctionSpan,
    sloc_lines: &BTreeSet<usize>,
    parts: LoweredFunctionParts<'_>,
) -> Function {
    Function {
        file: path.to_path_buf(),
        language,
        name: span.name.clone(),
        params: parts.params,
        start_line: span.start_line,
        end_line: span.end_line,
        sloc: function_sloc(span, sloc_lines),
        cyclomatic: span.cyclomatic,
        cognitive: span.cognitive,
        max_nesting: span.max_nesting,
        calls: call_sites(
            &numbered_body_lines(parts.body_lines, span.start_line),
            parts.call_keywords,
        ),
        body_shape: body_shape(&parts.body_statements),
    }
}

struct LoweredFunctionParts<'source> {
    params: Vec<String>,
    body_lines: &'source [&'source str],
    body_statements: Vec<&'source str>,
    call_keywords: &'static [&'static str],
}

fn signature_params(signature: &str, normalize: impl FnMut(&str) -> Option<String>) -> Vec<String> {
    let Some(start) = signature.find('(') else {
        return Vec::new();
    };
    let Some(end) = signature[start + 1..].find(')') else {
        return Vec::new();
    };
    signature[start + 1..start + 1 + end]
        .split(',')
        .filter_map(normalize)
        .collect()
}

fn function_sloc(span: &FunctionSpan, sloc_lines: &BTreeSet<usize>) -> usize {
    sloc_lines.range(span.start_line..=span.end_line).count()
}

fn numbered_body_lines<'line>(
    lines: &'line [&'line str],
    start_line: usize,
) -> Vec<(usize, &'line str)> {
    lines
        .iter()
        .enumerate()
        .map(|(offset, line)| (start_line + 1 + offset, *line))
        .collect()
}

fn call_sites(lines: &[(usize, &str)], keywords: &[&str]) -> Vec<CallSite> {
    let mut calls = Vec::new();
    for (line_number, line) in lines {
        for name in call_names(line, keywords) {
            calls.push(CallSite {
                name,
                line: *line_number,
                nesting: leading_nesting(line),
            });
        }
    }
    calls
}

fn body_shape(statements: &[&str]) -> BodyShape {
    if statements.len() != 1 {
        return BodyShape::Complex;
    }

    let statement = statements[0].trim().trim_end_matches(';').trim();
    let expression = statement
        .strip_prefix("return ")
        .unwrap_or(statement)
        .trim();

    if is_identifier(expression) {
        return BodyShape::IdentityReturn {
            value: expression.to_string(),
        };
    }

    if let Some((callee, args)) = call_expression(expression) {
        return BodyShape::CallReturn { callee, args };
    }

    BodyShape::Complex
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

fn leading_nesting(line: &str) -> usize {
    line.chars()
        .take_while(|character| *character == ' ')
        .count()
        / 4
}

fn call_names(line: &str, keywords: &[&str]) -> Vec<String> {
    let bytes = line.as_bytes();
    let mut calls = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        let Some((start, end)) = identifier_at(bytes, index) else {
            index += 1;
            continue;
        };
        if let Some(name) = call_name_at(line, start, end, keywords) {
            calls.push(name.to_string());
        }
        index = end;
    }
    calls
}

fn identifier_at(bytes: &[u8], index: usize) -> Option<(usize, usize)> {
    if !is_ident_start(bytes[index]) {
        return None;
    }
    let mut end = index + 1;
    while end < bytes.len() && is_ident_continue(bytes[end]) {
        end += 1;
    }
    Some((index, end))
}

fn call_name_at<'line>(
    line: &'line str,
    start: usize,
    end: usize,
    keywords: &[&str],
) -> Option<&'line str> {
    let bytes = line.as_bytes();
    let name = &line[start..end];
    let after = next_non_space(bytes, end);
    (after < bytes.len()
        && bytes[after] == b'('
        && is_bare_call(line, start)
        && !keywords.contains(&name))
    .then_some(name)
}

fn next_non_space(bytes: &[u8], mut index: usize) -> usize {
    while index < bytes.len() && bytes[index].is_ascii_whitespace() {
        index += 1;
    }
    index
}

fn is_bare_call(line: &str, start: usize) -> bool {
    let before = line[..start].trim_end();
    !before.ends_with('.') && !before.ends_with("::")
}

const fn is_ident_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

const fn is_ident_continue(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn call_expression(expression: &str) -> Option<(String, Vec<String>)> {
    let open = expression.find('(')?;
    let close = expression.rfind(')')?;
    if close < open {
        return None;
    }
    let callee = expression[..open].trim();
    if callee.is_empty() {
        return None;
    }
    let args = expression[open + 1..close]
        .split(',')
        .map(str::trim)
        .filter(|arg| !arg.is_empty())
        .map(ToString::to_string)
        .collect();
    Some((callee.to_string(), args))
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
    let mut stack = vec![node];
    while let Some(current) = stack.pop() {
        if is_clone_noise_node(source, current) {
            continue;
        }
        if let Some(token) = clone_leaf_token(source, current, names) {
            tokens.push(token);
            continue;
        }

        push_children_reverse(current, &mut stack);
    }
}

fn push_children_reverse<'tree>(node: Node<'tree>, stack: &mut Vec<Node<'tree>>) {
    for index in (0..node.child_count()).rev() {
        let Ok(index) = u32::try_from(index) else {
            continue;
        };
        if let Some(child) = node.child(index) {
            stack.push(child);
        }
    }
}

fn clone_leaf_token(
    source: &str,
    node: Node<'_>,
    names: &mut HashMap<String, String>,
) -> Option<String> {
    let kind = node.kind();
    if BaseParser::is_string_node(kind) {
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
        BaseParser::is_string_node(child.kind())
            || BaseParser::is_string_statement_text(source, child)
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

#[cfg(test)]
mod tests {
    use super::parse_syntax;
    use crate::model::Language;

    #[test]
    fn parser_finds_python_methods_and_rust_impl_methods() {
        let python = parse_syntax(
            Language::Python,
            r"
class Thing:
    def same(self, value):
        return value
",
        )
        .expect("python should parse");
        let rust = parse_syntax(
            Language::Rust,
            r"
struct Thing;

impl Thing {
    fn same(&self, value: i32) -> i32 {
        value
    }
}
",
        )
        .expect("rust should parse");

        assert_eq!(python.functions.len(), 1);
        assert_eq!(python.functions[0].name, "same");
        assert_eq!(python.functions[0].start_line, 3);
        assert_eq!(rust.functions.len(), 1);
        assert_eq!(rust.functions[0].name, "same");
        assert_eq!(rust.functions[0].start_line, 5);
    }

    #[test]
    fn complexity_metrics_ignore_branch_text_and_rust_match_arms() {
        let python = parse_syntax(
            Language::Python,
            r#"
def message():
    text = "if elif for while match and or"
    return text.upper()
"#,
        )
        .expect("python should parse");
        let rust = parse_syntax(
            Language::Rust,
            r#"
fn classify(value: i32) -> &'static str {
    match value {
        0 => "if for while loop match =>",
        1 => "one",
        _ => "many",
    }
}
"#,
        )
        .expect("rust should parse");

        assert_eq!(python.functions[0].cyclomatic, 1);
        assert_eq!(python.functions[0].cognitive, 0);
        assert_eq!(rust.functions[0].cyclomatic, 2);
        assert_eq!(rust.functions[0].cognitive, 1);
    }

    #[test]
    fn parser_rejects_syntax_error_trees() {
        let python = parse_syntax(Language::Python, "def broken(:\n    return 1\n");
        let rust = parse_syntax(Language::Rust, "fn broken( {\n    1\n}\n");

        assert!(python.is_err());
        assert!(rust.is_err());
    }
}

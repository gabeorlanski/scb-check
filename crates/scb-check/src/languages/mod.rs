use std::collections::{BTreeMap, BTreeSet, HashMap};

use tree_sitter::{Node, Tree};

use crate::model::Language;

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
    fn label(&self) -> &'static str;
    fn tree_sitter_language(&self) -> tree_sitter::Language;
    fn is_function_node(&self, kind: &str) -> bool;
    fn is_comment_node(&self, kind: &str) -> bool;
    fn build_function(&self, source: &str, node: Node<'_>) -> FunctionSpan;
    fn sloc_lines(&self, source: &str, root: Node<'_>, comments: &[CommentSpan])
    -> BTreeSet<usize>;

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
        Language::Python => python::parser::PYTHON_PARSER.parse(source),
        Language::Rust => rust::parser::RUST_PARSER.parse(source),
    }
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

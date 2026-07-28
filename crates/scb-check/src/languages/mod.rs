use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;

use ast_grep_language::SupportLang;
use tree_sitter::{Node, Tree};

use crate::model::{
    CallSite, Function, FunctionBody, FunctionId, ImportBinding, Language, ScopeId, ScopePath,
    SimpleCall, SimpleExpr, Visibility,
};

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
    pub qualified_name: String,
    pub visibility: Visibility,
    pub bare_call_scope: Option<ScopePath>,
    pub visible_bare_call_scopes: Vec<ScopePath>,
    pub has_receiver: bool,
    pub has_nontrivial_params: bool,
    pub start_line: usize,
    pub end_line: usize,
    pub cyclomatic: usize,
    pub cognitive: usize,
    pub max_nesting: usize,
    pub params: Vec<String>,
    pub calls: Vec<CallSite>,
    pub body: FunctionBody,
    pub clone_fingerprint: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedSyntax {
    pub functions: Vec<FunctionSpan>,
    pub imports: Vec<ImportBinding>,
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
    fn import_bindings(&self, path: &Path, source: &str, root: Node<'_>) -> Vec<ImportBinding>;
    fn sloc_lines(&self, source: &str, root: Node<'_>, comments: &[CommentSpan])
    -> BTreeSet<usize>;
    fn lower_function(
        &self,
        path: &Path,
        span: &FunctionSpan,
        _all_lines: &[&str],
        sloc_lines: &BTreeSet<usize>,
    ) -> Function {
        lower_function_from_span(path, self.language(), span, sloc_lines)
    }
    fn directive_text<'comment>(&self, comment: &'comment CommentSpan) -> Option<&'comment str>;

    fn parse(&self, path: &Path, source: &str) -> Result<ParsedSyntax, String>
    where
        Self: Sized,
    {
        BaseParser::new(self.label(), self.tree_sitter_language()).parse(self, path, source)
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
        path: &Path,
        source: &str,
    ) -> Result<ParsedSyntax, String> {
        let tree = self.parse_tree(source)?;
        let root = tree.root_node();
        if root.has_error() {
            return Err(format!("failed to parse {} source", self.label));
        }
        let functions = Self::collect_functions(language_parser, source, root);
        let imports = language_parser.import_bindings(path, source, root);
        let comments = Self::collect_comments(language_parser, source, root);
        let sloc_lines = language_parser.sloc_lines(source, root, &comments);
        Ok(ParsedSyntax {
            functions,
            imports,
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
        semantic: FunctionSemantic,
        facts: FunctionSyntaxFacts,
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
            qualified_name: semantic.qualified_name,
            visibility: semantic.visibility,
            bare_call_scope: semantic.bare_call_scope,
            visible_bare_call_scopes: semantic.visible_bare_call_scopes,
            has_receiver: facts.has_receiver,
            has_nontrivial_params: facts.has_nontrivial_params,
            start_line: node.start_position().row + 1,
            end_line: node.end_position().row + 1,
            cyclomatic,
            cognitive,
            max_nesting,
            params: facts.params,
            calls: facts.calls,
            body: facts.body,
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

    fn clone_fingerprint(source: &str, body: Node<'_>) -> Vec<String> {
        let mut names = HashMap::new();
        let mut cursor = body.walk();
        body.children(&mut cursor)
            .filter_map(|child| clone_statement_fingerprint(source, child, &mut names))
            .collect()
    }
}

#[cfg(test)]
fn parse_syntax(language: Language, source: &str) -> Result<ParsedSyntax, String> {
    let filename = match language {
        Language::Python => "sample.py",
        Language::Rust => "sample.rs",
    };
    parse_syntax_at_path(language, Path::new(filename), source)
}

pub fn parse_syntax_at_path(
    language: Language,
    path: &Path,
    source: &str,
) -> Result<ParsedSyntax, String> {
    match language {
        Language::Python => python::PYTHON_PARSER.parse(path, source),
        Language::Rust => rust::RUST_PARSER.parse(path, source),
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

pub const fn ast_grep_language(language: Language) -> Option<SupportLang> {
    match language {
        Language::Python => Some(SupportLang::Python),
        Language::Rust => None,
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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FunctionSemantic {
    pub qualified_name: String,
    pub visibility: Visibility,
    pub bare_call_scope: Option<ScopePath>,
    pub visible_bare_call_scopes: Vec<ScopePath>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FunctionSyntaxFacts {
    pub has_receiver: bool,
    pub has_nontrivial_params: bool,
    pub params: Vec<String>,
    pub calls: Vec<CallSite>,
    pub body: FunctionBody,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FunctionParams {
    pub has_receiver: bool,
    pub names: Vec<String>,
    pub has_nontrivial: bool,
}

pub fn function_syntax_facts(
    _source: &str,
    node: Node<'_>,
    params: impl Fn(Node<'_>) -> FunctionParams,
    is_function_node: impl Fn(&str) -> bool,
    callee_name: impl Fn(Node<'_>) -> Option<String>,
    increases_call_nesting: impl Fn(Node<'_>) -> bool,
    function_body: impl Fn(Node<'_>, &[String]) -> FunctionBody,
) -> FunctionSyntaxFacts {
    let body = node.child_by_field_name("body");
    let params = node
        .child_by_field_name("parameters")
        .map(params)
        .unwrap_or_default();
    FunctionSyntaxFacts {
        calls: body
            .map(|body| {
                collect_call_sites(body, is_function_node, callee_name, increases_call_nesting)
            })
            .unwrap_or_default(),
        body: body.map_or(FunctionBody::Complex, |body| {
            function_body(body, &params.names)
        }),
        has_receiver: params.has_receiver,
        has_nontrivial_params: params.has_nontrivial,
        params: params.names,
    }
}

fn lower_function_from_span(
    path: &Path,
    language: Language,
    span: &FunctionSpan,
    sloc_lines: &BTreeSet<usize>,
) -> Function {
    Function {
        id: FunctionId {
            file: path.to_path_buf(),
            qualified_name: span.qualified_name.clone(),
        },
        file: path.to_path_buf(),
        language,
        name: span.name.clone(),
        visibility: span.visibility,
        bare_call_scope: span.bare_call_scope.clone().map(|scope_path| ScopeId {
            file: path.to_path_buf(),
            path: scope_path,
        }),
        visible_bare_call_scopes: span
            .visible_bare_call_scopes
            .iter()
            .cloned()
            .map(|scope_path| ScopeId {
                file: path.to_path_buf(),
                path: scope_path,
            })
            .collect(),
        has_receiver: span.has_receiver,
        has_nontrivial_params: span.has_nontrivial_params,
        params: span.params.clone(),
        start_line: span.start_line,
        end_line: span.end_line,
        sloc: function_sloc(span, sloc_lines),
        cyclomatic: span.cyclomatic,
        cognitive: span.cognitive,
        max_nesting: span.max_nesting,
        calls: span.calls.clone(),
        body: span.body.clone(),
    }
}

fn function_sloc(span: &FunctionSpan, sloc_lines: &BTreeSet<usize>) -> usize {
    sloc_lines.range(span.start_line..=span.end_line).count()
}

pub fn collect_call_sites(
    body: Node<'_>,
    is_function_node: impl Fn(&str) -> bool,
    callee_name: impl Fn(Node<'_>) -> Option<String>,
    increases_call_nesting: impl Fn(Node<'_>) -> bool,
) -> Vec<CallSite> {
    let mut calls = Vec::new();
    let mut stack = Vec::new();
    push_children_reverse_with_nesting(body, 0, &mut stack);
    while let Some((node, nesting)) = stack.pop() {
        if is_function_node(node.kind()) {
            continue;
        }
        if let Some(name) = callee_name(node) {
            calls.push(CallSite {
                name,
                target: None,
                line: node.start_position().row + 1,
                nesting,
            });
        }
        let child_nesting = if increases_call_nesting(node) {
            nesting + 1
        } else {
            nesting
        };
        push_children_reverse_with_nesting(node, child_nesting, &mut stack);
    }
    calls
}

fn push_children_reverse_with_nesting<'tree>(
    node: Node<'tree>,
    nesting: usize,
    stack: &mut Vec<(Node<'tree>, usize)>,
) {
    for index in (0..node.child_count()).rev() {
        let Ok(index) = u32::try_from(index) else {
            continue;
        };
        if let Some(child) = node.child(index) {
            stack.push((child, nesting));
        }
    }
}

pub fn bare_call_name(
    source: &str,
    node: Node<'_>,
    call_kind: &str,
    callee_kind: &str,
) -> Option<String> {
    if node.kind() != call_kind {
        return None;
    }
    let function = node.child_by_field_name("function")?;
    (function.kind() == callee_kind).then(|| node_text(source, function))
}

pub fn call_body(source: &str, call: Node<'_>, params: &[String]) -> FunctionBody {
    let Some(function) = call.child_by_field_name("function") else {
        return FunctionBody::Complex;
    };
    let callee = node_text(source, function);
    if callee.is_empty() {
        return FunctionBody::Complex;
    }
    FunctionBody::SimpleReturn(SimpleExpr::Call(SimpleCall {
        callee,
        args: call
            .child_by_field_name("arguments")
            .map(|arguments| simple_arguments(source, arguments, params))
            .unwrap_or_default(),
    }))
}

pub fn simple_arguments(source: &str, arguments: Node<'_>, params: &[String]) -> Vec<SimpleExpr> {
    let mut cursor = arguments.walk();
    arguments
        .named_children(&mut cursor)
        .map(|argument| simple_expr(source, argument, params))
        .collect()
}

pub fn simple_expr(source: &str, expression: Node<'_>, params: &[String]) -> SimpleExpr {
    match expression.kind() {
        "identifier" => {
            let name = node_text(source, expression);
            if params.iter().any(|param| param == &name) {
                SimpleExpr::Param(name)
            } else {
                SimpleExpr::Unsupported
            }
        }
        kind if is_literal_node(kind) => SimpleExpr::Literal,
        _ => SimpleExpr::Unsupported,
    }
}

pub fn path_expr(source: &str, expression: Node<'_>) -> Option<Vec<String>> {
    let mut segments = Vec::new();
    let mut stack = vec![expression];
    while let Some(node) = stack.pop() {
        if matches!(
            node.kind(),
            "identifier" | "field_identifier" | "type_identifier"
        ) {
            segments.push(node_text(source, node));
            continue;
        }
        push_children_reverse(node, &mut stack);
    }
    (!segments.is_empty()).then_some(segments)
}

pub fn node_text(source: &str, node: Node<'_>) -> String {
    node.utf8_text(source.as_bytes())
        .unwrap_or_default()
        .to_string()
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
    matches!(node.kind(), "comment" | "line_comment" | "block_comment")
        || is_plain_string_statement(source, node)
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
    use crate::model::{FunctionBody, Language, ScopePath, SimpleCall, SimpleExpr, Visibility};

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
    fn parser_extracts_semantic_identity_and_node_facts() {
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
mod inner {
    fn clean(value: &str) -> String {
        value.trim().to_string()
    }

    fn route(value: &str) -> String {
        clean(value)
    }
}
",
        )
        .expect("rust should parse");

        assert_eq!(python.functions[0].qualified_name, "Thing.same");
        assert_eq!(python.functions[0].visibility, Visibility::Public);
        assert_eq!(python.functions[0].bare_call_scope, None);
        assert_eq!(python.functions[0].params, ["value"]);
        assert_eq!(
            python.functions[0].body,
            FunctionBody::SimpleReturn(SimpleExpr::Param("value".to_string()))
        );

        let route = rust
            .functions
            .iter()
            .find(|function| function.name == "route")
            .expect("route should be parsed");
        assert_eq!(route.qualified_name, "inner::route");
        assert_eq!(route.visibility, Visibility::Private);
        assert_eq!(
            route.bare_call_scope,
            Some(ScopePath {
                segments: vec!["inner".to_string()]
            })
        );
        assert_eq!(route.params, ["value"]);
        assert_eq!(route.calls.len(), 1);
        assert_eq!(route.calls[0].name, "clean");
        assert_eq!(
            route.body,
            FunctionBody::SimpleReturn(SimpleExpr::Call(SimpleCall {
                callee: "clean".to_string(),
                args: vec![SimpleExpr::Param("value".to_string())]
            }))
        );
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

    #[test]
    fn python_sloc_keeps_byte_and_f_string_statements() {
        let python = parse_syntax(
            Language::Python,
            r#"
"module docstring"
b"payload"
f"{value}"
r"plain raw string"
value = 1
"#,
        )
        .expect("python should parse");

        assert_eq!(python.sloc_lines, [3, 4, 6].into_iter().collect());
    }
}

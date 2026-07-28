use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use tree_sitter::Node;

use crate::languages::{
    BaseParser, CommentSpan, FunctionParams, FunctionSemantic, FunctionSpan, FunctionSyntaxFacts,
    LanguageParser, bare_call_name, call_body, function_syntax_facts, node_text, path_expr,
    push_children_reverse, simple_expr,
};
use crate::model::{FunctionBody, ImportBinding, Language, ScopePath, SimpleExpr, Visibility};

pub static RUST_PARSER: RustLanguageParser = RustLanguageParser;

#[derive(Debug, Clone, Copy)]
pub struct RustLanguageParser;

impl LanguageParser for RustLanguageParser {
    fn language(&self) -> Language {
        Language::Rust
    }

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
            Self::semantic(source, node),
            Self::syntax_facts(source, node),
            1 + Self::cyclomatic_increment(node),
            node.children(&mut node.walk())
                .map(|child| Self::cognitive_for_node(child, 0))
                .sum(),
            Self::max_nesting_for_node(node),
        )
    }

    fn import_bindings(&self, path: &Path, source: &str, root: Node<'_>) -> Vec<ImportBinding> {
        let mut bindings = Vec::new();
        let mut cursor = root.walk();
        for statement in root.named_children(&mut cursor) {
            if statement.kind() != "use_declaration" {
                continue;
            }
            if let Some(argument) = statement.child_by_field_name("argument") {
                collect_use_bindings(path, source, argument, &[], &mut bindings);
            }
        }
        bindings
    }

    fn sloc_lines(
        &self,
        source: &str,
        _root: Node<'_>,
        comments: &[CommentSpan],
    ) -> BTreeSet<usize> {
        BaseParser::generic_sloc_lines(source, comments)
    }

    fn directive_text<'comment>(&self, comment: &'comment CommentSpan) -> Option<&'comment str> {
        let text = comment.text.trim();
        text.strip_prefix("//")
            .map(str::trim)
            .or_else(|| Self::block_comment_text(text))
    }
}

fn collect_use_bindings(
    file: &Path,
    source: &str,
    clause: Node<'_>,
    prefix: &[String],
    bindings: &mut Vec<ImportBinding>,
) {
    match clause.kind() {
        "scoped_use_list" => {
            let mut scoped_prefix = prefix.to_vec();
            if let Some(path) = clause.child_by_field_name("path") {
                scoped_prefix.extend(path_expr(source, path).unwrap_or_default());
            }
            if let Some(list) = clause.child_by_field_name("list") {
                collect_use_bindings(file, source, list, &scoped_prefix, bindings);
            }
        }
        "use_list" => {
            let mut cursor = clause.walk();
            for child in clause.named_children(&mut cursor) {
                collect_use_bindings(file, source, child, prefix, bindings);
            }
        }
        "use_as_clause" => {
            let Some(path) = clause.child_by_field_name("path") else {
                return;
            };
            let Some(alias) = clause.child_by_field_name("alias") else {
                return;
            };
            let mut segments = prefix.to_vec();
            segments.extend(path_expr(source, path).unwrap_or_default());
            push_rust_import_binding(file, &segments, node_text(source, alias), bindings);
        }
        "identifier" | "scoped_identifier" => {
            let mut segments = prefix.to_vec();
            segments.extend(path_expr(source, clause).unwrap_or_default());
            let Some(local_name) = segments.last().cloned() else {
                return;
            };
            push_rust_import_binding(file, &segments, local_name, bindings);
        }
        _ => {}
    }
}

fn push_rust_import_binding(
    file: &Path,
    segments: &[String],
    local_name: String,
    bindings: &mut Vec<ImportBinding>,
) {
    let Some((target_name, module_segments)) = segments.split_last() else {
        return;
    };
    if module_segments.is_empty() {
        return;
    }
    let module_path: PathBuf = module_segments.iter().collect();
    let mut module_file = module_path.clone();
    module_file.set_extension("rs");
    bindings.push(ImportBinding {
        file: file.to_path_buf(),
        local_name,
        target_name: target_name.clone(),
        target_file_suffixes: vec![module_file, module_path.join("mod.rs")],
    });
}

impl RustLanguageParser {
    fn block_comment_text(text: &str) -> Option<&str> {
        let inner = text.strip_prefix("/*")?.strip_suffix("*/")?.trim();
        Some(inner.strip_prefix('*').unwrap_or(inner).trim())
    }

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

    fn semantic(source: &str, node: Node<'_>) -> FunctionSemantic {
        let name = node_name(source, node).unwrap_or_else(|| "<unknown>".to_string());
        let visibility = visibility_for_node(node);
        let ancestors = named_ancestor_scopes(source, node);
        let mut qualified_segments: Vec<String> =
            ancestors.iter().map(|scope| scope.name.clone()).collect();
        qualified_segments.push(name);
        let qualified_name = qualified_segments.join("::");
        let enclosing_functions: Vec<ScopePath> = ancestors
            .iter()
            .filter(|scope| scope.kind == RustScopeKind::Function)
            .map(|scope| scope.path.clone())
            .collect();
        let module_scope = ancestors
            .iter()
            .rev()
            .find(|scope| scope.kind == RustScopeKind::Module)
            .map(|scope| scope.path.clone())
            .unwrap_or_default();
        let has_non_bare_container = ancestors
            .iter()
            .any(|scope| matches!(scope.kind, RustScopeKind::Impl | RustScopeKind::Trait));
        let bare_call_scope = enclosing_functions
            .last()
            .cloned()
            .or_else(|| (!has_non_bare_container).then_some(module_scope.clone()));
        let mut visible_bare_call_scopes = Vec::new();
        visible_bare_call_scopes.push(ScopePath {
            segments: qualified_segments,
        });
        visible_bare_call_scopes.extend(enclosing_functions.into_iter().rev());
        if !module_scope.segments.is_empty() {
            visible_bare_call_scopes.push(module_scope);
        }
        visible_bare_call_scopes.push(ScopePath::default());
        FunctionSemantic {
            qualified_name,
            visibility,
            bare_call_scope,
            visible_bare_call_scopes,
        }
    }

    fn syntax_facts(source: &str, node: Node<'_>) -> FunctionSyntaxFacts {
        function_syntax_facts(
            source,
            node,
            |parameters| Self::params(source, parameters),
            Self::is_nested_function,
            |call| Self::bare_call_name(source, call),
            Self::is_complexity_node,
            |body, params| Self::body(source, body, params),
        )
    }

    fn params(source: &str, parameters: Node<'_>) -> FunctionParams {
        let mut params = Vec::new();
        let mut has_receiver = false;
        let mut cursor = parameters.walk();
        for child in parameters.named_children(&mut cursor) {
            if child.kind() == "self_parameter" {
                has_receiver = true;
                continue;
            }
            if let Some(name) = pattern_identifier_text(source, child) {
                params.push(name);
            }
        }
        FunctionParams {
            has_receiver,
            names: params,
            has_nontrivial: false,
        }
    }

    fn is_nested_function(kind: &str) -> bool {
        kind == "function_item"
    }

    fn bare_call_name(source: &str, node: Node<'_>) -> Option<String> {
        bare_call_name(source, node, "call_expression", "identifier")
    }

    fn body(source: &str, body: Node<'_>, params: &[String]) -> FunctionBody {
        let statements = meaningful_body_statements(body);
        if statements.len() != 1 {
            return FunctionBody::Complex;
        }
        expression_body(source, return_or_expression_child(statements[0]), params)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RustScopeKind {
    Function,
    Impl,
    Module,
    Trait,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NamedScope {
    name: String,
    path: ScopePath,
    kind: RustScopeKind,
}

fn named_ancestor_scopes(source: &str, node: Node<'_>) -> Vec<NamedScope> {
    let mut ancestors = Vec::new();
    let mut parent = node.parent();
    while let Some(current) = parent {
        let scope = match current.kind() {
            "function_item" => {
                node_name(source, current).map(|name| (RustScopeKind::Function, name))
            }
            "impl_item" => impl_name(source, current).map(|name| (RustScopeKind::Impl, name)),
            "mod_item" => node_name(source, current).map(|name| (RustScopeKind::Module, name)),
            "trait_item" => node_name(source, current).map(|name| (RustScopeKind::Trait, name)),
            _ => None,
        };
        if let Some(scope) = scope {
            ancestors.push(scope);
        }
        parent = current.parent();
    }
    ancestors.reverse();

    let mut qualified = Vec::new();
    ancestors
        .into_iter()
        .map(|(kind, name)| {
            qualified.push(name.clone());
            NamedScope {
                name,
                path: ScopePath {
                    segments: qualified.clone(),
                },
                kind,
            }
        })
        .collect()
}

fn node_name(source: &str, node: Node<'_>) -> Option<String> {
    node.child_by_field_name("name")
        .map(|name| node_text(source, name))
}

fn visibility_for_node(node: Node<'_>) -> Visibility {
    let mut cursor = node.walk();
    if node
        .children(&mut cursor)
        .any(|child| child.kind() == "visibility_modifier")
    {
        Visibility::Public
    } else {
        Visibility::Private
    }
}

fn impl_name(source: &str, node: Node<'_>) -> Option<String> {
    node.child_by_field_name("type")
        .or_else(|| first_named_child_of_kind(node, "type_identifier"))
        .map(|name| node_text(source, name))
}

fn first_named_child_of_kind<'tree>(node: Node<'tree>, kind: &str) -> Option<Node<'tree>> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor)
        .find(|child| child.kind() == kind)
}

fn meaningful_body_statements(body: Node<'_>) -> Vec<Node<'_>> {
    let mut cursor = body.walk();
    body.named_children(&mut cursor)
        .filter(|child| {
            !matches!(
                child.kind(),
                "line_comment" | "block_comment" | "function_item"
            )
        })
        .collect()
}

fn return_or_expression_child(statement: Node<'_>) -> Node<'_> {
    if statement.kind() == "return_expression" || statement.kind() == "expression_statement" {
        statement.named_child(0).unwrap_or(statement)
    } else {
        statement
    }
}

fn expression_body(source: &str, expression: Node<'_>, params: &[String]) -> FunctionBody {
    match expression.kind() {
        "call_expression" => call_body(source, expression, params),
        "identifier" => {
            let name = node_text(source, expression);
            if params.iter().any(|param| param == &name) {
                FunctionBody::SimpleReturn(SimpleExpr::Param(name))
            } else if is_constant_name(&name) {
                FunctionBody::SimpleReturn(SimpleExpr::Constant)
            } else {
                FunctionBody::Complex
            }
        }
        "scoped_identifier" => {
            if path_expr(source, expression)
                .and_then(|segments| segments.last().cloned())
                .is_some_and(|name| is_constant_name(&name))
            {
                FunctionBody::SimpleReturn(SimpleExpr::Constant)
            } else {
                FunctionBody::Complex
            }
        }
        "integer_literal" | "float_literal" | "char_literal" | "boolean_literal"
        | "string_literal" | "raw_string_literal" => {
            FunctionBody::SimpleReturn(simple_expr(source, expression, params))
        }
        _ => FunctionBody::Complex,
    }
}

fn is_constant_name(name: &str) -> bool {
    name.chars()
        .any(|character| character.is_ascii_alphabetic())
        && name.chars().all(|character| {
            character.is_ascii_uppercase() || character.is_ascii_digit() || character == '_'
        })
}

fn pattern_identifier_text(source: &str, node: Node<'_>) -> Option<String> {
    if node.kind() == "identifier" {
        return Some(node_text(source, node));
    }
    if let Some(pattern) = node.child_by_field_name("pattern") {
        return first_identifier_text(source, pattern);
    }
    first_identifier_text(source, node)
}

fn first_identifier_text(source: &str, node: Node<'_>) -> Option<String> {
    let mut stack = vec![node];
    while let Some(current) = stack.pop() {
        if current.kind() == "identifier" {
            return Some(node_text(source, current));
        }
        push_children_reverse(current, &mut stack);
    }
    None
}

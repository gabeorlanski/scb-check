use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use tree_sitter::Node;

use crate::languages::{
    BaseParser, CommentSpan, FunctionParams, FunctionSemantic, FunctionSpan, FunctionSyntaxFacts,
    LanguageParser, bare_call_name, call_body, function_syntax_facts, node_text,
    push_children_reverse, simple_expr,
};
use crate::model::{FunctionBody, ImportBinding, Language, ScopePath, SimpleExpr, Visibility};

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
        let mut cursor = root.walk();
        root.named_children(&mut cursor)
            .filter(|statement| statement.kind() == "import_from_statement")
            .flat_map(|statement| python_import_from_statement(path, source, statement))
            .collect()
    }

    fn sloc_lines(
        &self,
        source: &str,
        root: Node<'_>,
        _comments: &[CommentSpan],
    ) -> BTreeSet<usize> {
        Self::python_sloc_lines(source, root)
    }

    fn directive_text<'comment>(&self, comment: &'comment CommentSpan) -> Option<&'comment str> {
        comment.text.strip_prefix('#').map(str::trim)
    }
}

fn python_module_file_suffixes(module_segments: &[&str]) -> Vec<PathBuf> {
    if module_segments.is_empty() {
        return Vec::new();
    }
    let module_path: PathBuf = module_segments.iter().collect();
    let mut module_file = module_path.clone();
    module_file.set_extension("py");
    vec![module_file, module_path.join("__init__.py")]
}

fn python_import_from_statement(
    path: &Path,
    source: &str,
    statement: Node<'_>,
) -> Vec<ImportBinding> {
    let Some(module) = statement.child_by_field_name("module_name") else {
        return Vec::new();
    };
    let module_text = node_text(source, module);
    let module_segments: Vec<&str> = module_text
        .trim_start_matches('.')
        .split('.')
        .filter(|segment| !segment.is_empty())
        .collect();
    let target_file_suffixes = python_module_file_suffixes(&module_segments);
    let mut cursor = statement.walk();
    statement
        .named_children(&mut cursor)
        .filter(|imported| imported.id() != module.id() && imported.kind() != "wildcard_import")
        .filter_map(|imported| {
            let (target, local) = if imported.kind() == "aliased_import" {
                (
                    node_text(source, imported.child_by_field_name("name")?),
                    node_text(source, imported.child_by_field_name("alias")?),
                )
            } else {
                let target = node_text(source, imported);
                let local = target.split('.').next()?.to_string();
                (target, local)
            };
            Some(ImportBinding {
                file: path.to_path_buf(),
                local_name: local,
                target_name: target.rsplit('.').next()?.to_string(),
                target_file_suffixes: target_file_suffixes.clone(),
            })
        })
        .collect()
}

impl PythonLanguageParser {
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
            && Self::is_plain_string_literal(source, literal)
            && Self::owns_line(literal, source_lines))
        .then_some(literal)
    }

    fn is_plain_string_literal(source: &str, literal: Node<'_>) -> bool {
        let mut stack = vec![literal];
        while let Some(node) = stack.pop() {
            if BaseParser::is_string_node(node.kind()) {
                let text = node
                    .utf8_text(source.as_bytes())
                    .unwrap_or_default()
                    .trim_start();
                let prefix = text
                    .split_once(['\'', '"'])
                    .map_or("", |(prefix, _)| prefix);
                if prefix
                    .chars()
                    .any(|character| matches!(character.to_ascii_lowercase(), 'b' | 'f'))
                {
                    return false;
                }
            }
            push_children_reverse(node, &mut stack);
        }
        true
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

    fn semantic(source: &str, node: Node<'_>) -> FunctionSemantic {
        let name = node_name(source, node).unwrap_or_else(|| "<unknown>".to_string());
        let visibility = visibility_for_name(&name);
        let ancestors = named_ancestor_scopes(source, node);
        let mut qualified_segments: Vec<String> =
            ancestors.iter().map(|scope| scope.name.clone()).collect();
        qualified_segments.push(name);
        let qualified_name = qualified_segments.join(".");
        let enclosing_functions: Vec<ScopePath> = ancestors
            .iter()
            .filter(|scope| scope.kind == PythonScopeKind::Function)
            .map(|scope| scope.path.clone())
            .collect();
        let bare_call_scope = enclosing_functions
            .last()
            .cloned()
            .or_else(|| ancestors.is_empty().then(ScopePath::default));
        let mut visible_bare_call_scopes = Vec::new();
        visible_bare_call_scopes.push(ScopePath {
            segments: qualified_segments,
        });
        visible_bare_call_scopes.extend(enclosing_functions.into_iter().rev());
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
            |node| Self::is_cognitive_flow_break_node(node.kind()),
            |body, params| Self::body(source, body, params),
        )
    }

    fn params(source: &str, parameters: Node<'_>) -> FunctionParams {
        let mut params = Vec::new();
        let mut has_receiver = false;
        let mut has_nontrivial = false;
        let mut cursor = parameters.walk();
        for child in parameters.named_children(&mut cursor) {
            has_nontrivial |= python_parameter_has_nontrivial_semantics(child);
            if let Some(name) = first_identifier_text(source, child) {
                if matches!(name.as_str(), "self" | "cls") {
                    has_receiver = true;
                } else {
                    params.push(name);
                }
            }
        }
        FunctionParams {
            has_receiver,
            names: params,
            has_nontrivial,
        }
    }

    fn is_nested_function(kind: &str) -> bool {
        kind == "function_definition"
    }

    fn bare_call_name(source: &str, node: Node<'_>) -> Option<String> {
        bare_call_name(source, node, "call", "identifier")
    }

    fn body(source: &str, body: Node<'_>, params: &[String]) -> FunctionBody {
        let statements = meaningful_body_statements(body);
        if statements.len() != 1 {
            return FunctionBody::Complex;
        }
        let expression = return_or_expression_child(statements[0]);
        expression.map_or(FunctionBody::Complex, |expression| {
            expression_body(source, expression, params)
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PythonScopeKind {
    Class,
    Function,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NamedScope {
    name: String,
    path: ScopePath,
    kind: PythonScopeKind,
}

fn named_ancestor_scopes(source: &str, node: Node<'_>) -> Vec<NamedScope> {
    let mut ancestors = Vec::new();
    let mut parent = node.parent();
    while let Some(current) = parent {
        let kind = match current.kind() {
            "class_definition" => Some(PythonScopeKind::Class),
            "function_definition" => Some(PythonScopeKind::Function),
            _ => None,
        };
        if let Some(kind) =
            kind.and_then(|kind| node_name(source, current).map(|name| (kind, name)))
        {
            ancestors.push(kind);
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

fn visibility_for_name(name: &str) -> Visibility {
    if name.starts_with('_') {
        Visibility::Private
    } else {
        Visibility::Public
    }
}

fn python_parameter_has_nontrivial_semantics(parameter: Node<'_>) -> bool {
    let mut stack = vec![parameter];
    while let Some(node) = stack.pop() {
        if matches!(
            node.kind(),
            "default_parameter"
                | "typed_default_parameter"
                | "list_splat_pattern"
                | "dictionary_splat_pattern"
                | "keyword_separator"
                | "positional_separator"
                | "tuple_pattern"
        ) {
            return true;
        }
        push_children_reverse(node, &mut stack);
    }
    false
}

fn meaningful_body_statements(body: Node<'_>) -> Vec<Node<'_>> {
    let mut cursor = body.walk();
    body.named_children(&mut cursor)
        .filter(|child| !matches!(child.kind(), "comment" | "function_definition"))
        .filter(|child| {
            !(child.kind() == "expression_statement"
                && child.named_child(0).is_some_and(|grandchild| {
                    matches!(grandchild.kind(), "string" | "concatenated_string")
                }))
        })
        .collect()
}

fn return_or_expression_child(statement: Node<'_>) -> Option<Node<'_>> {
    match statement.kind() {
        "return_statement" | "expression_statement" => statement.named_child(0),
        _ => Some(statement),
    }
}

fn expression_body(source: &str, expression: Node<'_>, params: &[String]) -> FunctionBody {
    match expression.kind() {
        "call" => call_body(source, expression, params),
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
        "string" | "integer" | "float" | "true" | "false" | "none" => {
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

fn first_identifier_text(source: &str, node: Node<'_>) -> Option<String> {
    if node.kind() == "identifier" {
        return Some(node_text(source, node));
    }
    let mut stack = vec![node];
    while let Some(current) = stack.pop() {
        if current.kind() == "identifier" {
            return Some(node_text(source, current));
        }
        push_children_reverse(current, &mut stack);
    }
    None
}

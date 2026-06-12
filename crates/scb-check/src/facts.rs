use std::collections::BTreeSet;
use std::path::Path;

use crate::languages::FunctionSpan;
use crate::model::{BodyShape, CallSite, Function, Language};

pub fn build_function(
    path: &Path,
    language: Language,
    span: &FunctionSpan,
    all_lines: &[&str],
    sloc_lines: &BTreeSet<usize>,
) -> Function {
    let lines = function_lines(span, all_lines);
    let sloc = sloc_lines.range(span.start_line..=span.end_line).count();
    let body_lines = body_line_entries(language, lines, span.start_line);

    Function {
        file: path.to_path_buf(),
        language,
        name: span.name.clone(),
        params: function_params(language, &span.signature),
        start_line: span.start_line,
        end_line: span.end_line,
        sloc,
        cyclomatic: span.cyclomatic,
        cognitive: span.cognitive,
        max_nesting: span.max_nesting,
        calls: call_sites(language, &body_lines),
        body_shape: body_shape(language, lines),
    }
}

pub fn function_lines<'a>(span: &FunctionSpan, all_lines: &'a [&'a str]) -> &'a [&'a str] {
    if all_lines.is_empty() {
        return &[];
    }
    let start_index = span.start_line.saturating_sub(1).min(all_lines.len() - 1);
    let end_index = span.end_line.saturating_sub(1).min(all_lines.len() - 1);
    &all_lines[start_index..=end_index.max(start_index)]
}

fn leading_nesting(line: &str) -> usize {
    line.chars()
        .take_while(|character| *character == ' ')
        .count()
        / 4
}

fn function_params(language: Language, signature_line: &str) -> Vec<String> {
    let Some(start) = signature_line.find('(') else {
        return Vec::new();
    };
    let Some(end) = signature_line[start + 1..].find(')') else {
        return Vec::new();
    };
    let raw_params = &signature_line[start + 1..start + 1 + end];
    raw_params
        .split(',')
        .filter_map(|param| normalize_param(language, param))
        .collect()
}

fn normalize_param(language: Language, param: &str) -> Option<String> {
    let param = param.trim();
    if param.is_empty() {
        return None;
    }
    match language {
        Language::Python => {
            let name = param.split([':', '=']).next().unwrap_or_default().trim();
            (!name.is_empty() && name != "self" && name != "cls").then(|| name.to_string())
        }
        Language::Rust => {
            let name = param
                .split(':')
                .next()
                .unwrap_or_default()
                .trim()
                .trim_start_matches("mut ")
                .trim();
            (!name.is_empty() && name != "self" && name != "&self" && name != "&mut self")
                .then(|| name.to_string())
        }
    }
}

fn body_shape(language: Language, lines: &[&str]) -> BodyShape {
    let statements = body_statements(language, lines);
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

fn body_statements<'a>(language: Language, lines: &'a [&str]) -> Vec<&'a str> {
    body_lines(language, lines)
        .iter()
        .map(|line| line.trim())
        .filter(|line| !line.is_empty())
        .filter(|line| !line.starts_with('#') && !line.starts_with("//"))
        .filter(|line| !matches!(*line, "{" | "}"))
        .collect()
}

fn body_line_entries<'a>(
    language: Language,
    lines: &'a [&'a str],
    start_line: usize,
) -> Vec<(usize, &'a str)> {
    let body_start = match language {
        Language::Python => usize::from(!lines.is_empty()),
        Language::Rust => usize::from(lines.len() > 2),
    };
    body_lines(language, lines)
        .iter()
        .enumerate()
        .map(|(offset, line)| (start_line + body_start + offset, *line))
        .collect()
}

fn body_lines<'a>(language: Language, lines: &'a [&str]) -> &'a [&'a str] {
    match language {
        Language::Python => {
            if lines.len() <= 1 {
                &[]
            } else {
                &lines[1..]
            }
        }
        Language::Rust => rust_body_lines(lines),
    }
}

fn rust_body_lines<'a>(lines: &'a [&str]) -> &'a [&'a str] {
    if lines.len() <= 2 {
        return &[];
    }
    &lines[1..lines.len() - 1]
}

fn call_sites(language: Language, lines: &[(usize, &str)]) -> Vec<CallSite> {
    let mut calls = Vec::new();
    for (line_number, line) in lines {
        for name in call_names(line, language) {
            calls.push(CallSite {
                name,
                line: *line_number,
                nesting: leading_nesting(line),
            });
        }
    }
    calls
}

fn call_names(line: &str, language: Language) -> Vec<String> {
    let bytes = line.as_bytes();
    let mut calls = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        let Some((start, end)) = identifier_at(bytes, index) else {
            index += 1;
            continue;
        };
        if let Some(name) = call_name_at(line, start, end, language) {
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

fn call_name_at(line: &str, start: usize, end: usize, language: Language) -> Option<&str> {
    let bytes = line.as_bytes();
    let name = &line[start..end];
    let after = next_non_space(bytes, end);
    (after < bytes.len()
        && bytes[after] == b'('
        && is_bare_call(line, start)
        && !is_call_keyword(name, language))
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

fn is_call_keyword(name: &str, language: Language) -> bool {
    match language {
        Language::Python => matches!(
            name,
            "if" | "elif"
                | "for"
                | "while"
                | "return"
                | "raise"
                | "with"
                | "def"
                | "class"
                | "lambda"
                | "not"
                | "and"
                | "or"
        ),
        Language::Rust => matches!(
            name,
            "if" | "for" | "while" | "loop" | "match" | "return" | "fn" | "let" | "async" | "move"
        ),
    }
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

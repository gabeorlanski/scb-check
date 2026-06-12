use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::languages::CommentSpan;
use crate::model::{AstGrepFinding, Function, StructuralFinding};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IgnoreDirective {
    file: PathBuf,
    target_line: usize,
    rule_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundaryDirective {
    file: PathBuf,
    directive_line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedDirectives {
    pub ignores: Vec<IgnoreDirective>,
    pub boundaries: Vec<BoundaryDirective>,
}

pub fn parse_source_directives(
    path: &Path,
    source: &str,
    comments: &[CommentSpan],
    valid_rule_ids: &BTreeSet<String>,
) -> Result<ParsedDirectives, String> {
    let lines: Vec<&str> = source.lines().collect();
    let code_lines = code_lines(&lines, comments);
    let mut ignores = Vec::new();
    let mut boundaries = Vec::new();
    let mut errors = Vec::new();

    for comment in comments {
        let has_code_before = has_code_before_comment(&lines, comment);
        match parse_directive_comment(path, comment, has_code_before, &code_lines, valid_rule_ids) {
            Ok(Some(ParsedDirectiveLine::Ignore(ignore))) => ignores.push(ignore),
            Ok(Some(ParsedDirectiveLine::Boundary(boundary))) => boundaries.push(boundary),
            Ok(None) => {}
            Err(message) => errors.push(message),
        }
    }

    if errors.is_empty() {
        Ok(ParsedDirectives {
            ignores,
            boundaries,
        })
    } else {
        Err(errors.join("\n"))
    }
}

enum ParsedDirectiveLine {
    Ignore(IgnoreDirective),
    Boundary(BoundaryDirective),
}

fn parse_directive_comment(
    path: &Path,
    comment: &CommentSpan,
    has_code_before: bool,
    code_lines: &BTreeSet<usize>,
    valid_rule_ids: &BTreeSet<String>,
) -> Result<Option<ParsedDirectiveLine>, String> {
    let comment_text = comment
        .text
        .strip_prefix('#')
        .unwrap_or(&comment.text)
        .trim();
    if !comment_text.starts_with("scbc") {
        return Ok(None);
    }
    if let Some(raw_rule_ids) = ignore_rule_ids(comment_text) {
        return parse_ignore(
            path,
            comment.line,
            raw_rule_ids,
            has_code_before,
            code_lines,
            valid_rule_ids,
        )
        .map(|ignore| Some(ParsedDirectiveLine::Ignore(ignore)));
    }
    if is_boundary(comment_text) {
        return Ok(Some(ParsedDirectiveLine::Boundary(BoundaryDirective {
            file: path.to_path_buf(),
            directive_line: comment.line,
        })));
    }
    Ok(None)
}

pub fn filter_ast_grep_findings(
    findings: Vec<AstGrepFinding>,
    ignores: &[IgnoreDirective],
    boundaries: &[BoundaryDirective],
    functions: &[Function],
) -> Result<Vec<AstGrepFinding>, String> {
    let boundary_ranges = boundary_ranges(boundaries, functions)?;
    Ok(findings
        .into_iter()
        .filter(|finding| !is_ignored(&finding.file, finding.start_line, &finding.rule_id, ignores))
        .filter(|finding| !is_boundary_suppressed(finding, &boundary_ranges))
        .collect())
}

pub fn filter_structural_findings(
    findings: Vec<StructuralFinding>,
    ignores: &[IgnoreDirective],
) -> Vec<StructuralFinding> {
    findings
        .into_iter()
        .filter(|finding| !is_ignored(&finding.file, finding.start_line, finding.rule_id, ignores))
        .collect()
}

fn code_lines(lines: &[&str], comments: &[CommentSpan]) -> BTreeSet<usize> {
    let comment_by_line = comments
        .iter()
        .map(|comment| (comment.line, comment.column))
        .collect::<std::collections::BTreeMap<_, _>>();
    lines
        .iter()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_number = index + 1;
            let code = comment_by_line
                .get(&line_number)
                .and_then(|column| line.get(..*column))
                .unwrap_or(line)
                .trim();
            (!code.is_empty()).then_some(index + 1)
        })
        .collect()
}

fn has_code_before_comment(lines: &[&str], comment: &CommentSpan) -> bool {
    lines
        .get(comment.line.saturating_sub(1))
        .and_then(|line| line.get(..comment.column))
        .is_some_and(|prefix| !prefix.trim().is_empty())
}

fn ignore_rule_ids(comment: &str) -> Option<&str> {
    let rest = comment.strip_prefix("scbc ignore[")?;
    rest.split(']').next()
}

fn is_boundary(comment: &str) -> bool {
    comment == "scbc boundary"
        || comment.strip_prefix("scbc boundary").is_some_and(|suffix| {
            suffix.starts_with(':') || suffix.starts_with(char::is_whitespace)
        })
}

fn parse_ignore(
    path: &Path,
    directive_line: usize,
    raw_rule_ids: &str,
    has_code_before: bool,
    code_lines: &BTreeSet<usize>,
    valid_rule_ids: &BTreeSet<String>,
) -> Result<IgnoreDirective, String> {
    let rule_ids = validated_rule_ids(path, directive_line, raw_rule_ids, valid_rule_ids)?;
    let target_line = if has_code_before {
        Some(directive_line)
    } else {
        code_lines.range((directive_line + 1)..).next().copied()
    };
    let Some(target_line) = target_line else {
        return Err(format!(
            "{}:{}: scbc ignore has no target code line",
            path.display(),
            directive_line
        ));
    };
    Ok(IgnoreDirective {
        file: path.to_path_buf(),
        target_line,
        rule_ids,
    })
}

fn validated_rule_ids(
    path: &Path,
    line_number: usize,
    raw_rule_ids: &str,
    valid_rule_ids: &BTreeSet<String>,
) -> Result<Vec<String>, String> {
    let mut rule_ids = Vec::new();
    for rule_id in raw_rule_ids.split(',').map(str::trim) {
        if rule_id.is_empty() || rule_ids.iter().any(|existing| existing == rule_id) {
            continue;
        }
        validate_rule_id(path, line_number, rule_id, valid_rule_ids)?;
        rule_ids.push(rule_id.to_string());
    }
    require_rule_ids(path, line_number, &rule_ids)?;
    Ok(rule_ids)
}

fn validate_rule_id(
    path: &Path,
    line_number: usize,
    rule_id: &str,
    valid_rule_ids: &BTreeSet<String>,
) -> Result<(), String> {
    if rule_id == "*" {
        return Err(format!(
            "{}:{}: wildcard ignores are not supported",
            path.display(),
            line_number
        ));
    }
    if !valid_rule_ids.contains(rule_id) {
        return Err(format!(
            "{}:{}: unknown rule id: {}",
            path.display(),
            line_number,
            rule_id
        ));
    }
    Ok(())
}

fn require_rule_ids(path: &Path, line_number: usize, rule_ids: &[String]) -> Result<(), String> {
    if rule_ids.is_empty() {
        return Err(format!(
            "{}:{}: scbc ignore requires at least one rule id",
            path.display(),
            line_number
        ));
    }
    Ok(())
}

fn boundary_ranges(
    boundaries: &[BoundaryDirective],
    functions: &[Function],
) -> Result<Vec<(PathBuf, usize, usize)>, String> {
    let mut ranges = Vec::new();
    let mut errors = Vec::new();
    for boundary in boundaries {
        match containing_function(boundary, functions) {
            Some(function) => ranges.push((
                function.file.clone(),
                function.start_line,
                function.end_line,
            )),
            None => errors.push(format!(
                "{}:{}: scbc boundary must be inside a function body",
                boundary.file.display(),
                boundary.directive_line
            )),
        }
    }
    if errors.is_empty() {
        Ok(ranges)
    } else {
        Err(errors.join("\n"))
    }
}

fn containing_function<'a>(
    boundary: &BoundaryDirective,
    functions: &'a [Function],
) -> Option<&'a Function> {
    functions
        .iter()
        .filter(|function| {
            function.file == boundary.file
                && function_body_range(function).contains(&boundary.directive_line)
        })
        .min_by_key(|function| function.end_line)
}

const fn function_body_range(function: &Function) -> std::ops::RangeInclusive<usize> {
    function.start_line.saturating_add(1)..=function.end_line
}

fn is_boundary_suppressed(finding: &AstGrepFinding, ranges: &[(PathBuf, usize, usize)]) -> bool {
    ranges.iter().any(|(file, start_line, end_line)| {
        finding.file == *file
            && *start_line <= finding.start_line
            && finding.start_line <= *end_line
    })
}

fn is_ignored(file: &Path, line: usize, rule_id: &str, ignores: &[IgnoreDirective]) -> bool {
    ignores.iter().any(|ignore| {
        ignore.file == file
            && ignore.target_line == line
            && ignore.rule_ids.iter().any(|id| id == rule_id)
    })
}

#[cfg(test)]
mod tests {
    use crate::test_support::{analyze_dir, test_dir, write};

    #[test]
    fn source_ignore_directives_suppress_ast_grep_and_structural_findings() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
def noisy(items):
    for index in range(len(items)):  # scbc ignore[for-range-len] intentional index access
        print(items[index])

# scbc ignore[trivial-wrapper]
def identity(value):
    return value
",
        );

        let report = analyze_dir(&root, false, false, None).expect("analysis should succeed");
        assert!(!report.has_findings());

        let include_all =
            analyze_dir(&root, false, true, None).expect("include-all analysis should succeed");
        assert!(
            include_all
                .ast_grep_findings
                .iter()
                .any(|finding| finding.rule_id == "for-range-len")
        );
        assert!(
            include_all
                .structural_findings
                .iter()
                .any(|finding| finding.rule_id == "trivial-wrapper")
        );
    }

    #[test]
    fn boundary_directive_suppresses_ast_grep_inside_function() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
def noisy(items):
    # scbc boundary: framework callback input shape
    for index in range(len(items)):
        print(items[index])
",
        );

        let report = analyze_dir(&root, false, false, None).expect("analysis should succeed");
        assert!(!report.has_findings());

        let include_all =
            analyze_dir(&root, false, true, None).expect("include-all analysis should succeed");
        assert!(
            include_all
                .ast_grep_findings
                .iter()
                .any(|finding| finding.rule_id == "for-range-len")
        );
    }

    #[test]
    fn invalid_source_directive_is_usage_error() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
# scbc ignore[not-a-rule]
value = 1
",
        );

        let error = analyze_dir(&root, false, false, None).expect_err("directive should fail");

        assert!(error.contains("unknown rule id: not-a-rule"));
    }

    #[test]
    fn source_directive_text_inside_python_string_is_ignored() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r##"
def marker():
    return "# scbc ignore[not-a-rule]"

# scbc ignore[trivial-wrapper]
def identity(value):
    return value
"##,
        );

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");

        assert!(!report.has_findings());
    }
}

use std::collections::BTreeSet;
use std::fmt;
use std::path::{Path, PathBuf};

use thiserror::Error;

use crate::languages::{CommentSpan, directive_text};
use crate::model::{AstGrepFinding, Function, Language, StructuralFinding};

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

#[derive(Debug, Error)]
enum DirectiveIssue {
    #[error("{}:{line}: scbc ignore has no target code line", path.display())]
    NoTargetCode { path: PathBuf, line: usize },
    #[error("{}:{line}: wildcard ignores are not supported", path.display())]
    WildcardIgnore { path: PathBuf, line: usize },
    #[error("{}:{line}: unknown rule id: {rule_id}", path.display())]
    UnknownRule {
        path: PathBuf,
        line: usize,
        rule_id: String,
    },
    #[error("{}:{line}: scbc ignore requires at least one rule id", path.display())]
    MissingRuleIds { path: PathBuf, line: usize },
    #[error("{}:{line}: scbc boundary must be inside a function body", path.display())]
    BoundaryOutsideFunction { path: PathBuf, line: usize },
}

#[derive(Debug)]
pub struct DirectiveError {
    issues: Vec<DirectiveIssue>,
}

impl DirectiveError {
    const fn from_issues(issues: Vec<DirectiveIssue>) -> Self {
        Self { issues }
    }
}

impl fmt::Display for DirectiveError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        for (index, issue) in self.issues.iter().enumerate() {
            if index > 0 {
                writeln!(formatter)?;
            }
            write!(formatter, "{issue}")?;
        }
        Ok(())
    }
}

impl std::error::Error for DirectiveError {}

/// Parse supported source directives from the comments in one source file.
///
/// Parsed directives own their file paths and rule identifiers because filtering occurs later,
/// after the borrowed source text and comment spans have been discarded.
pub fn parse_source_directives(
    language: Language,
    path: &Path,
    source: &str,
    comments: &[CommentSpan],
    valid_rule_ids: &BTreeSet<String>,
) -> Result<ParsedDirectives, DirectiveError> {
    let lines: Vec<&str> = source.lines().collect();
    let code_lines = code_lines(&lines, comments);
    let mut ignores = Vec::new();
    let mut boundaries = Vec::new();
    let mut issues = Vec::new();

    for comment in comments {
        let has_code_before = has_code_before_comment(&lines, comment);
        let Some(comment_text) = directive_text(language, comment) else {
            continue;
        };
        match parse_directive_comment(
            path,
            comment.line,
            comment_text,
            has_code_before,
            &code_lines,
            valid_rule_ids,
        ) {
            Ok(Some(ParsedDirectiveLine::Ignore(ignore))) => ignores.push(ignore),
            Ok(Some(ParsedDirectiveLine::Boundary(boundary))) => boundaries.push(boundary),
            Ok(None) => {}
            Err(issue) => issues.push(issue),
        }
    }

    if issues.is_empty() {
        Ok(ParsedDirectives {
            ignores,
            boundaries,
        })
    } else {
        Err(DirectiveError::from_issues(issues))
    }
}

enum ParsedDirectiveLine {
    Ignore(IgnoreDirective),
    Boundary(BoundaryDirective),
}

fn parse_directive_comment(
    path: &Path,
    line: usize,
    comment_text: &str,
    has_code_before: bool,
    code_lines: &BTreeSet<usize>,
    valid_rule_ids: &BTreeSet<String>,
) -> Result<Option<ParsedDirectiveLine>, DirectiveIssue> {
    if !comment_text.starts_with("scbc") {
        return Ok(None);
    }
    if let Some(raw_rule_ids) = ignore_rule_ids(comment_text) {
        return parse_ignore(
            path,
            line,
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
            directive_line: line,
        })));
    }
    Ok(None)
}

/// Validate boundary directives and apply suppression to ast-grep findings unless `include_all`.
///
/// Boundary directives are always validated; `include_all` then returns every finding unchanged.
pub fn filter_ast_grep_findings(
    findings: Vec<AstGrepFinding>,
    ignores: &[IgnoreDirective],
    boundaries: &[BoundaryDirective],
    functions: &[Function],
    include_all: bool,
) -> Result<Vec<AstGrepFinding>, DirectiveError> {
    let boundary_ranges = boundary_ranges(boundaries, functions)?;
    if include_all {
        return Ok(findings);
    }
    Ok(findings
        .into_iter()
        .filter(|finding| !is_ignored(&finding.file, finding.start_line, &finding.rule_id, ignores))
        .filter(|finding| !is_boundary_suppressed(finding, &boundary_ranges))
        .collect())
}

/// Return structural findings not suppressed by ignore directives.
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
    let mut comment_intervals = std::collections::BTreeMap::<usize, Vec<(usize, usize)>>::new();
    for comment in comments {
        for line in comment.line..=comment.end_line {
            let start = if line == comment.line {
                comment.column
            } else {
                0
            };
            let end = if line == comment.end_line {
                comment.end_column
            } else {
                usize::MAX
            };
            comment_intervals
                .entry(line)
                .or_default()
                .push((start, end));
        }
    }
    lines
        .iter()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_number = index + 1;
            let intervals = comment_intervals
                .get(&line_number)
                .map(Vec::as_slice)
                .unwrap_or_default();
            let mut cursor = 0;
            let has_code = intervals.iter().any(|(start, end)| {
                let bounded_start = (*start).min(line.len());
                let before = line[cursor..bounded_start].trim();
                cursor = cursor.max((*end).min(line.len()));
                !before.is_empty()
            }) || !line[cursor..].trim().is_empty();
            has_code.then_some(line_number)
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
) -> Result<IgnoreDirective, DirectiveIssue> {
    let rule_ids = validated_rule_ids(path, directive_line, raw_rule_ids, valid_rule_ids)?;
    let target_line = if has_code_before {
        Some(directive_line)
    } else {
        code_lines.range((directive_line + 1)..).next().copied()
    };
    let Some(target_line) = target_line else {
        return Err(DirectiveIssue::NoTargetCode {
            path: path.to_path_buf(),
            line: directive_line,
        });
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
) -> Result<Vec<String>, DirectiveIssue> {
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
) -> Result<(), DirectiveIssue> {
    if rule_id == "*" {
        return Err(DirectiveIssue::WildcardIgnore {
            path: path.to_path_buf(),
            line: line_number,
        });
    }
    if !valid_rule_ids.contains(rule_id) {
        return Err(DirectiveIssue::UnknownRule {
            path: path.to_path_buf(),
            line: line_number,
            rule_id: rule_id.to_string(),
        });
    }
    Ok(())
}

fn require_rule_ids(
    path: &Path,
    line_number: usize,
    rule_ids: &[String],
) -> Result<(), DirectiveIssue> {
    if rule_ids.is_empty() {
        return Err(DirectiveIssue::MissingRuleIds {
            path: path.to_path_buf(),
            line: line_number,
        });
    }
    Ok(())
}

fn boundary_ranges(
    boundaries: &[BoundaryDirective],
    functions: &[Function],
) -> Result<Vec<(PathBuf, usize, usize)>, DirectiveError> {
    let mut ranges = Vec::new();
    let mut issues = Vec::new();
    for boundary in boundaries {
        match containing_function(boundary, functions) {
            Some(function) => ranges.push((
                function.file.clone(),
                function.start_line,
                function.end_line,
            )),
            None => issues.push(DirectiveIssue::BoundaryOutsideFunction {
                path: boundary.file.clone(),
                line: boundary.directive_line,
            }),
        }
    }
    if issues.is_empty() {
        Ok(ranges)
    } else {
        Err(DirectiveError::from_issues(issues))
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

    fn assert_source_has_no_findings(filename: &str, source: &str) {
        let root = test_dir();
        write(&root.join(filename), source);

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");

        assert!(!report.has_findings());
    }

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
def _identity(value):
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
    fn invalid_source_directives_are_usage_errors_even_with_include_all() {
        for (source, include_all, expected) in [
            (
                r"
# scbc ignore[not-a-rule]
value = 1
",
                false,
                "unknown rule id: not-a-rule",
            ),
            (
                r"
# scbc boundary
value = 1
",
                true,
                "scbc boundary must be inside a function body",
            ),
        ] {
            let root = test_dir();
            write(&root.join("sample.py"), source);
            let error =
                analyze_dir(&root, false, include_all, None).expect_err("directive should fail");

            assert!(error.to_string().contains(expected));
        }
    }

    #[test]
    fn source_directive_text_inside_python_string_is_ignored() {
        assert_source_has_no_findings(
            "sample.py",
            r##"
def marker():
    return "# scbc ignore[not-a-rule]"

# scbc ignore[trivial-wrapper]
def identity(value):
    return value
"##,
        );
    }

    #[test]
    fn rust_line_comment_directives_suppress_structural_findings() {
        assert_source_has_no_findings(
            "sample.rs",
            r"
// scbc ignore[trivial-wrapper]
fn identity(value: i32) -> i32 {
    value
}
",
        );
    }

    #[test]
    fn rust_ignore_skips_every_line_of_a_multiline_block_comment() {
        assert_source_has_no_findings(
            "sample.rs",
            r"
// scbc ignore[trivial-wrapper]
/* explanatory comment
 * continued explanation
 */
fn identity(value: i32) -> i32 {
    value
}
",
        );
    }
}

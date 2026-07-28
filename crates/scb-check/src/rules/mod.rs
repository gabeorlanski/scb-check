pub mod base;

#[path = "low-use-short-function.rs"]
mod low_use_short_function;
#[path = "trivial-wrapper.rs"]
mod trivial_wrapper;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{CallGraph, Function, StructuralFinding};
use crate::rules::base::{RuleContext, RuleMetadata, Violation};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rule {
    TrivialWrapper,
    LowUseShortFunction,
}

const ALL_RULES: [Rule; 2] = [Rule::TrivialWrapper, Rule::LowUseShortFunction];

impl Rule {
    const fn all() -> &'static [Self] {
        &ALL_RULES
    }

    const fn metadata(self) -> RuleMetadata {
        match self {
            Self::TrivialWrapper => trivial_wrapper::TrivialWrapper::METADATA,
            Self::LowUseShortFunction => low_use_short_function::LowUseShortFunction::METADATA,
        }
    }

    fn check(self, context: &RuleContext<'_>, findings: &mut Vec<StructuralFinding>) {
        match self {
            Self::TrivialWrapper => trivial_wrapper::check(context, findings),
            Self::LowUseShortFunction => low_use_short_function::check(context, findings),
        }
    }
}

pub fn structural_rule_ids() -> Vec<&'static str> {
    Rule::all().iter().map(|rule| rule.metadata().id).collect()
}

pub fn structural_rule_document(rule_id: &str) -> Option<String> {
    let rule = Rule::all()
        .iter()
        .find(|rule| rule.metadata().id == rule_id)?;
    Some(base::structural_rule_document(rule.metadata()))
}

pub fn run_structural_rules(
    functions: &[Function],
    call_graph: &CallGraph,
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Vec<StructuralFinding> {
    let context = RuleContext {
        functions,
        call_graph,
        low_use_short_function,
    };
    let mut findings = Vec::new();
    for rule in Rule::all() {
        rule.check(&context, &mut findings);
    }
    findings
}

#[cfg(test)]
mod tests {
    use super::structural_rule_document;
    use crate::test_support::{analyze_dir, test_dir, write};

    #[test]
    fn shared_structural_wrapper_rule_runs_on_python_and_rust_facts() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
def _identity(value):
    return value

def _forward(value):
    return _identity(value)

def branch(value):
    if value:
        return value
    return None

def _duplicate_forward(left, right):
    return _identity(left, left)

def _default_identity(value=DEFAULT):
    return value

def _variadic_identity(*values):
    return values

def _swap(left, right):
    return _identity(right, left)
",
        );
        write(
            &root.join("sample.rs"),
            r"
fn identity(value: i32) -> i32 {
    value
}

fn forward(value: i32) -> i32 {
    identity(value)
}

fn branch(value: i32) -> i32 {
    if value > 0 {
        return value;
    }
    0
}

fn duplicate_forward(left: i32, right: i32) -> i32 {
    identity(left, left)
}
",
        );

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");

        assert_eq!(
            report
                .structural_findings
                .iter()
                .filter(|finding| finding.rule_id == "trivial-wrapper")
                .count(),
            4
        );
        assert!(
            report
                .structural_findings
                .iter()
                .any(|finding| finding.file.ends_with("sample.py") && finding.start_line == 1)
        );
        assert!(
            report
                .structural_findings
                .iter()
                .any(|finding| finding.file.ends_with("sample.rs") && finding.start_line == 5)
        );
        assert!(
            report
                .structural_findings
                .iter()
                .all(|finding| finding.subject_name != "branch")
        );
        assert!(
            report
                .structural_findings
                .iter()
                .all(|finding| finding.subject_name != "_duplicate_forward"
                    && finding.subject_name != "duplicate_forward")
        );
        assert!(
            report
                .structural_findings
                .iter()
                .all(|finding| finding.subject_name != "_default_identity"
                    && finding.subject_name != "_variadic_identity"
                    && finding.subject_name != "_swap")
        );
    }

    #[test]
    fn trivial_wrapper_flags_constant_return_helpers() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
DEFAULT_CONTEXT_LINES = 4

def _default_context_lines():
    return DEFAULT_CONTEXT_LINES
",
        );
        write(
            &root.join("sample.rs"),
            r"
const DEFAULT_CONTEXT_LINES: usize = 4;

const fn default_context_lines() -> usize {
    DEFAULT_CONTEXT_LINES
}
",
        );

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");
        let constant_helpers = report
            .structural_findings
            .iter()
            .filter(|finding| {
                finding.rule_id == "trivial-wrapper"
                    && matches!(
                        finding.subject_name.as_str(),
                        "_default_context_lines" | "default_context_lines"
                    )
            })
            .count();

        assert_eq!(constant_helpers, 2);
    }

    #[test]
    fn low_use_short_function_is_opt_in_and_runs_on_python_and_rust_facts() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
def clean(value):
    normalized = value.strip()
    return normalized

def route(value):
    return clean(value)
",
        );
        write(
            &root.join("sample.rs"),
            r"
fn clean(value: &str) -> String {
    let normalized = value.trim();
    normalized.to_string()
}

fn route(value: &str) -> String {
    clean(value)
}
",
        );

        let default_report =
            analyze_dir(&root, true, false, None).expect("analysis should succeed");
        assert!(
            default_report
                .structural_findings
                .iter()
                .all(|finding| finding.rule_id != "low-use-short-function")
        );

        let config = root.join("scb-check.toml");
        write(&config, "[low-use-short-function]\nenabled = true\n");
        let enabled_report =
            analyze_dir(&root, true, false, Some(&config)).expect("analysis should succeed");

        let low_use_findings: Vec<_> = enabled_report
            .structural_findings
            .iter()
            .filter(|finding| finding.rule_id == "low-use-short-function")
            .collect();
        assert_eq!(low_use_findings.len(), 2);
        assert!(
            low_use_findings
                .iter()
                .all(|finding| finding.start_line == 1)
        );
        assert!(
            low_use_findings
                .iter()
                .all(|finding| finding.fix_title.as_deref() == Some("Inline `clean`"))
        );
    }

    #[test]
    fn low_use_short_function_resolves_same_named_functions_by_file() {
        let root = test_dir();
        write(
            &root.join("a.py"),
            r"
def clean(value):
    normalized = value.strip()
    return normalized

def route(value):
    return clean(value)
",
        );
        write(
            &root.join("b.py"),
            r"
def clean(value):
    normalized = value.lower()
    return normalized
",
        );
        write(
            &root.join("a.rs"),
            r"
fn clean(value: &str) -> String {
    let normalized = value.trim();
    normalized.to_string()
}

fn route(value: &str) -> String {
    clean(value)
}
",
        );
        write(
            &root.join("b.rs"),
            r"
fn clean(value: &str) -> String {
    let normalized = value.to_lowercase();
    normalized
}
",
        );
        let config = root.join("scb-check.toml");
        write(&config, "[low-use-short-function]\nenabled = true\n");

        let report =
            analyze_dir(&root, true, false, Some(&config)).expect("analysis should succeed");

        let mut low_use_files: Vec<_> = report
            .structural_findings
            .iter()
            .filter(|finding| finding.rule_id == "low-use-short-function")
            .map(|finding| {
                finding
                    .file
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .to_string()
            })
            .collect();
        low_use_files.sort();

        assert_eq!(low_use_files, ["a.py", "a.rs"]);
    }

    #[test]
    fn low_use_short_function_counts_calls_through_project_imports() {
        let root = test_dir();
        write(
            &root.join("helpers.py"),
            r"
def _clean(value):
    normalized = value.strip()
    return normalized

def local_route(value):
    return _clean(value)
",
        );
        for filename in ["first.py", "second.py"] {
            write(
                &root.join(filename),
                r"
from helpers import _clean

def route(value):
    return _clean(value)
",
            );
        }
        write(
            &root.join("helpers.rs"),
            r"
fn clean(value: &str) -> String {
    let normalized = value.trim();
    normalized.to_string()
}

fn local_route(value: &str) -> String {
    clean(value)
}
",
        );
        for filename in ["first.rs", "second.rs"] {
            write(
                &root.join(filename),
                r"
use crate::helpers::clean;

fn route(value: &str) -> String {
    clean(value)
}
",
            );
        }
        let config = root.join("scb-check.toml");
        write(&config, "[low-use-short-function]\nenabled = true\n");

        let report =
            analyze_dir(&root, true, false, Some(&config)).expect("analysis should succeed");

        assert!(
            report
                .structural_findings
                .iter()
                .all(|finding| !matches!(finding.subject_name.as_str(), "_clean" | "clean"))
        );
    }

    #[test]
    fn structural_rule_document_prints_registered_metadata() {
        let document =
            structural_rule_document("trivial-wrapper").expect("rule document should exist");

        insta::assert_snapshot!(
            document,
            @r###"
id: trivial-wrapper
severity: warning
target: symbol
kind: structural
message: Function adds no behavior.
"###
        );
    }
}

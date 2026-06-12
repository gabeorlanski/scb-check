pub(crate) mod base;

#[path = "low-use-short-function.rs"]
mod low_use_short_function;
#[path = "trivial-wrapper.rs"]
mod trivial_wrapper;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, StructuralFinding};
use crate::rules::base::{RuleContext, RuleMetadata, Violation};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Rule {
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

pub(crate) fn structural_rule_ids() -> Vec<&'static str> {
    Rule::all().iter().map(|rule| rule.metadata().id).collect()
}

pub(crate) fn structural_rule_document(rule_id: &str) -> Option<String> {
    let rule = Rule::all()
        .iter()
        .find(|rule| rule.metadata().id == rule_id)?;
    Some(base::structural_rule_document(rule.metadata()))
}

pub(crate) fn run_structural_rules(
    functions: &[Function],
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Vec<StructuralFinding> {
    let context = RuleContext {
        functions,
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
def identity(value):
    return value

def forward(value):
    return identity(value)

def branch(value):
    if value:
        return value
    return None
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

use std::path::PathBuf;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, StructuralFinding};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct StructuralRuleMetadata {
    pub id: &'static str,
    pub severity: &'static str,
    pub target: &'static str,
    pub message: &'static str,
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct RuleContext<'a> {
    pub functions: &'a [Function],
    pub low_use_short_function: &'a LowUseShortFunctionSettings,
}

pub(crate) trait Rule: Sync {
    fn metadata(&self) -> StructuralRuleMetadata;
    fn check(&self, context: &RuleContext<'_>) -> Vec<StructuralFinding>;
}

pub(crate) trait Violation {
    const METADATA: StructuralRuleMetadata;

    fn message(&self) -> String;
}

pub(crate) trait AlwaysFixableViolation: Violation {
    fn fix_title(&self) -> String;
}

pub(crate) trait SometimesFixableViolation: Violation {
    fn fix_title(&self) -> Option<String>;
}

pub(crate) fn structural_rule_document(metadata: StructuralRuleMetadata) -> String {
    format!(
        "id: {}\nseverity: {}\ntarget: {}\nkind: structural\nmessage: {}\n",
        metadata.id, metadata.severity, metadata.target, metadata.message
    )
}

pub(crate) fn finding<V: Violation>(
    violation: &V,
    file: PathBuf,
    start_line: usize,
    end_line: usize,
    subject_name: String,
    fix_title: Option<String>,
) -> StructuralFinding {
    StructuralFinding {
        rule_id: V::METADATA.id,
        severity: V::METADATA.severity,
        message: violation.message(),
        fix_title,
        file,
        start_line,
        end_line,
        subject_name,
    }
}

pub(crate) fn always_fix_title<V: AlwaysFixableViolation>(violation: &V) -> String {
    violation.fix_title()
}

pub(crate) fn sometimes_fix_title<V: SometimesFixableViolation>(violation: &V) -> Option<String> {
    violation.fix_title()
}

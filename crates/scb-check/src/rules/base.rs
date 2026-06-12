use std::path::PathBuf;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, StructuralFinding};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum FixAvailability {
    None,
    Sometimes,
    Always,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct RuleMetadata {
    pub(crate) id: &'static str,
    pub(crate) severity: &'static str,
    pub(crate) target: &'static str,
    pub(crate) message: &'static str,
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct RuleContext<'a> {
    pub(crate) functions: &'a [Function],
    pub(crate) low_use_short_function: &'a LowUseShortFunctionSettings,
}

pub(crate) trait Violation {
    const METADATA: RuleMetadata;
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::None;

    fn message(&self) -> String;

    fn fix_title(&self) -> Option<String> {
        None
    }
}

pub(crate) struct Diagnostic<V: Violation> {
    violation: V,
    file: PathBuf,
    start_line: usize,
    end_line: usize,
    subject_name: String,
}

impl<V: Violation> Diagnostic<V> {
    pub(crate) const fn new(
        violation: V,
        file: PathBuf,
        start_line: usize,
        end_line: usize,
        subject_name: String,
    ) -> Self {
        Self {
            violation,
            file,
            start_line,
            end_line,
            subject_name,
        }
    }

    pub(crate) fn into_finding(self) -> StructuralFinding {
        let fix_title = match V::FIX_AVAILABILITY {
            FixAvailability::None => None,
            FixAvailability::Sometimes | FixAvailability::Always => self.violation.fix_title(),
        };
        StructuralFinding {
            rule_id: V::METADATA.id,
            severity: V::METADATA.severity,
            message: self.violation.message(),
            fix_title,
            file: self.file,
            start_line: self.start_line,
            end_line: self.end_line,
            subject_name: self.subject_name,
        }
    }
}

pub(crate) fn structural_rule_document(metadata: RuleMetadata) -> String {
    format!(
        "id: {}\nseverity: {}\ntarget: {}\nkind: structural\nmessage: {}\n",
        metadata.id, metadata.severity, metadata.target, metadata.message
    )
}

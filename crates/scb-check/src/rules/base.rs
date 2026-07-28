use std::path::PathBuf;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{CallGraph, Function, StructuralFinding};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FixAvailability {
    None,
    Sometimes,
    Always,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RuleMetadata {
    pub id: &'static str,
    pub severity: &'static str,
    pub target: &'static str,
    pub message: &'static str,
}

#[derive(Debug, Clone, Copy)]
pub struct RuleContext<'a> {
    pub functions: &'a [Function],
    pub call_graph: &'a CallGraph,
    pub low_use_short_function: &'a LowUseShortFunctionSettings,
}

pub trait Violation {
    const METADATA: RuleMetadata;
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::None;

    /// Render the rule-specific diagnostic message.
    fn message(&self) -> String;

    /// Return a remediation title when this violation can be fixed.
    fn fix_title(&self) -> Option<String> {
        None
    }
}

pub struct Diagnostic<V: Violation> {
    violation: V,
    file: PathBuf,
    start_line: usize,
    end_line: usize,
    subject_name: String,
}

impl<V: Violation> Diagnostic<V> {
    /// Construct a structural diagnostic with its source location and subject.
    ///
    /// The diagnostic takes ownership of the violation, path, and subject because it represents a
    /// durable rule result that is converted only after rule evaluation completes.
    pub const fn new(
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

    /// Consume this diagnostic and produce the report-facing structural finding.
    ///
    /// This moves the owned location and subject data into the finding while deriving its message
    /// and optional fix title from the violation before dropping it.
    pub fn into_finding(self) -> StructuralFinding {
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

/// Format structural-rule metadata as the same document shape used by ast-grep rules.
pub fn structural_rule_document(metadata: RuleMetadata) -> String {
    format!(
        "id: {}\nseverity: {}\ntarget: {}\nkind: structural\nmessage: {}\n",
        metadata.id, metadata.severity, metadata.target, metadata.message
    )
}

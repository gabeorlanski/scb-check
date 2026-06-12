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

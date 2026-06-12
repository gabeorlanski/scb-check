pub(crate) mod base;

#[path = "low-use-short-function.rs"]
mod low_use_short_function;
#[path = "trivial-wrapper.rs"]
mod trivial_wrapper;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, StructuralFinding};
use crate::rules::base::StructuralRuleMetadata;

const STRUCTURAL_RULES: &[StructuralRuleMetadata] =
    &[trivial_wrapper::METADATA, low_use_short_function::METADATA];

pub(crate) fn structural_rule_ids() -> Vec<&'static str> {
    STRUCTURAL_RULES
        .iter()
        .map(|metadata| metadata.id)
        .collect()
}

pub(crate) fn structural_rule_document(rule_id: &str) -> Option<String> {
    let metadata = STRUCTURAL_RULES
        .iter()
        .find(|metadata| metadata.id == rule_id)?;
    Some(base::structural_rule_document(*metadata))
}

pub(crate) fn run_structural_rules(
    functions: &[Function],
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Vec<StructuralFinding> {
    let mut findings = trivial_wrapper::check(functions);
    findings.extend(low_use_short_function::check(
        functions,
        low_use_short_function,
    ));
    findings
}

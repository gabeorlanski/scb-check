pub(crate) mod base;

#[path = "low-use-short-function.rs"]
mod low_use_short_function;
#[path = "trivial-wrapper.rs"]
mod trivial_wrapper;

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, StructuralFinding};
use crate::rules::base::{Rule, RuleContext};

fn structural_rules() -> [&'static dyn Rule; 2] {
    [&trivial_wrapper::RULE, &low_use_short_function::RULE]
}

pub(crate) fn structural_rule_ids() -> Vec<&'static str> {
    structural_rules()
        .iter()
        .map(|rule| rule.metadata().id)
        .collect()
}

pub(crate) fn structural_rule_document(rule_id: &str) -> Option<String> {
    let rules = structural_rules();
    let rule = rules
        .into_iter()
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
    structural_rules()
        .iter()
        .flat_map(|rule| rule.check(&context))
        .collect()
}

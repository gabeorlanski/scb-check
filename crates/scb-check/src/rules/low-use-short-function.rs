use crate::config::LowUseShortFunctionSettings;
use crate::model::{CallSite, Function, StructuralFinding};
use crate::rules::base::StructuralRuleMetadata;

pub(crate) const METADATA: StructuralRuleMetadata = StructuralRuleMetadata {
    id: "low-use-short-function",
    severity: "info",
    target: "symbol",
    message: "Short low-use function can be inlined safely.",
};

pub(crate) fn check(
    functions: &[Function],
    settings: &LowUseShortFunctionSettings,
) -> Vec<StructuralFinding> {
    if !settings.enabled {
        return Vec::new();
    }

    functions
        .iter()
        .filter_map(|function| low_use_short_function(function, functions, settings))
        .collect()
}

fn low_use_short_function(
    function: &Function,
    functions: &[Function],
    settings: &LowUseShortFunctionSettings,
) -> Option<StructuralFinding> {
    if function.sloc > settings.max_function_sloc {
        return None;
    }

    let call_sites = call_sites_for(function, functions);
    if call_sites.is_empty() || call_sites.len() > settings.max_call_sites {
        return None;
    }
    if !callers_stay_within_budgets(function, &call_sites, settings) {
        return None;
    }

    Some(StructuralFinding {
        rule_id: METADATA.id,
        severity: METADATA.severity,
        message: low_use_message(&function.name, call_sites.len()),
        file: function.file.clone(),
        start_line: function.start_line,
        end_line: function.end_line,
        subject_name: function.name.clone(),
    })
}

fn call_sites_for<'a>(
    function: &Function,
    functions: &'a [Function],
) -> Vec<(&'a Function, &'a CallSite)> {
    functions
        .iter()
        .filter(|caller| caller.file != function.file || caller.start_line != function.start_line)
        .flat_map(|caller| {
            caller
                .calls
                .iter()
                .filter(|call| call.name == function.name)
                .map(move |call| (caller, call))
        })
        .collect()
}

fn callers_stay_within_budgets(
    function: &Function,
    call_sites: &[(&Function, &CallSite)],
    settings: &LowUseShortFunctionSettings,
) -> bool {
    call_sites.iter().all(|(caller, call)| {
        let call_count = call_sites
            .iter()
            .filter(|(other, _)| other.file == caller.file && other.start_line == caller.start_line)
            .count();
        caller.sloc + inline_sloc_delta(function) * call_count <= settings.max_inline_caller_sloc
            && caller.cyclomatic + inline_cyclomatic_delta(function) * call_count
                <= settings.max_inline_caller_complexity
            && caller.cognitive + function.cognitive * call_count
                <= settings.max_inline_caller_cognitive_complexity
            && caller.max_nesting.max(call.nesting + function.max_nesting)
                <= settings.max_inline_call_nesting
    })
}

const fn inline_sloc_delta(function: &Function) -> usize {
    function.sloc.saturating_sub(1)
}

const fn inline_cyclomatic_delta(function: &Function) -> usize {
    function.cyclomatic.saturating_sub(1)
}

fn low_use_message(name: &str, call_sites: usize) -> String {
    let noun = if call_sites == 1 {
        "call site"
    } else {
        "call sites"
    };
    format!("`{name}` is short and used at {call_sites} {noun}; inline it")
}

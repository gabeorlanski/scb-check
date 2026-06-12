use crate::config::LowUseShortFunctionSettings;
use crate::model::{CallSite, Function, StructuralFinding};
use crate::rules::base::{Diagnostic, FixAvailability, RuleContext, RuleMetadata, Violation};

pub struct LowUseShortFunction {
    function_name: String,
    call_sites: usize,
}

impl Violation for LowUseShortFunction {
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::Sometimes;
    const METADATA: RuleMetadata = RuleMetadata {
        id: "low-use-short-function",
        severity: "info",
        target: "symbol",
        message: "Short low-use function can be inlined safely.",
    };

    fn message(&self) -> String {
        let noun = if self.call_sites == 1 {
            "call site"
        } else {
            "call sites"
        };
        format!(
            "`{}` is short and used at {} {noun}; inline it",
            self.function_name, self.call_sites
        )
    }

    fn fix_title(&self) -> Option<String> {
        Some(format!("Inline `{}`", self.function_name))
    }
}

pub fn check(context: &RuleContext<'_>, findings: &mut Vec<StructuralFinding>) {
    if context.low_use_short_function.enabled {
        findings.extend(context.functions.iter().filter_map(|function| {
            low_use_short_function(function, context.functions, context.low_use_short_function)
        }));
    }
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

    Some(
        Diagnostic::new(
            LowUseShortFunction {
                function_name: function.name.clone(),
                call_sites: call_sites.len(),
            },
            function.file.clone(),
            function.start_line,
            function.end_line,
            function.name.clone(),
        )
        .into_finding(),
    )
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

use crate::config::LowUseShortFunctionSettings;
use crate::model::{Function, ResolvedCall, StructuralFinding};
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
        findings.extend(
            context
                .functions
                .iter()
                .filter_map(|function| low_use_short_function(function, context)),
        );
    }
}

fn low_use_short_function(
    function: &Function,
    context: &RuleContext<'_>,
) -> Option<StructuralFinding> {
    let settings = context.low_use_short_function;
    if function.sloc > settings.max_function_sloc {
        return None;
    }

    let call_sites = context
        .call_graph
        .incoming_to(context.functions, &function.id)
        .into_iter()
        .filter(|call| call.caller.id != function.id)
        .collect::<Vec<_>>();
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

fn callers_stay_within_budgets(
    function: &Function,
    call_sites: &[ResolvedCall<'_>],
    settings: &LowUseShortFunctionSettings,
) -> bool {
    let inline_sloc_delta = function.sloc.saturating_sub(1);
    let inline_cyclomatic_delta = function.cyclomatic.saturating_sub(1);

    call_sites.iter().all(|resolved_call| {
        let caller = resolved_call.caller;
        let call = resolved_call.call;
        let call_count = call_sites
            .iter()
            .filter(|other| other.caller.id == caller.id)
            .count();
        caller.sloc + inline_sloc_delta * call_count <= settings.max_inline_caller_sloc
            && caller.cyclomatic + inline_cyclomatic_delta * call_count
                <= settings.max_inline_caller_complexity
            && caller.cognitive + function.cognitive * call_count
                <= settings.max_inline_caller_cognitive_complexity
            && caller.max_nesting.max(call.nesting + function.max_nesting)
                <= settings.max_inline_call_nesting
    })
}

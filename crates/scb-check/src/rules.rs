use crate::config::LowUseShortFunctionSettings;
use crate::model::{BodyShape, CallSite, Function, StructuralFinding};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct StructuralRuleMetadata {
    id: &'static str,
    severity: &'static str,
    target: &'static str,
    message: &'static str,
    capabilities: &'static [RuleCapability],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RuleCapability {
    FunctionFacts,
    CallSites,
}

#[derive(Debug, Clone, Copy)]
struct RuleContext<'a> {
    functions: &'a [Function],
    low_use_short_function: &'a LowUseShortFunctionSettings,
}

trait StructuralRule {
    fn metadata(&self) -> StructuralRuleMetadata;
    fn check(&self, context: &RuleContext<'_>) -> Vec<StructuralFinding>;
}

#[derive(Debug, Clone, Copy)]
struct TrivialWrapperRule;

#[derive(Debug, Clone, Copy)]
struct LowUseShortFunctionRule;

const TRIVIAL_WRAPPER_METADATA: StructuralRuleMetadata = StructuralRuleMetadata {
    id: "trivial-wrapper",
    severity: "warning",
    target: "symbol",
    message: "Function adds no behavior.",
    capabilities: &[RuleCapability::FunctionFacts],
};

const LOW_USE_SHORT_FUNCTION_METADATA: StructuralRuleMetadata = StructuralRuleMetadata {
    id: "low-use-short-function",
    severity: "info",
    target: "symbol",
    message: "Short low-use function can be inlined safely.",
    capabilities: &[RuleCapability::FunctionFacts, RuleCapability::CallSites],
};

pub(crate) fn structural_rule_ids() -> Vec<&'static str> {
    structural_rule_metadata()
        .iter()
        .map(|metadata| metadata.id)
        .collect()
}

pub(crate) fn structural_rule_document(rule_id: &str) -> Option<String> {
    let metadata = structural_rule_metadata()
        .iter()
        .find(|metadata| metadata.id == rule_id)?;
    Some(format!(
        "id: {}\nseverity: {}\ntarget: {}\nkind: structural\nmessage: {}\n",
        metadata.id, metadata.severity, metadata.target, metadata.message
    ))
}

pub(crate) fn run_structural_rules(
    functions: &[Function],
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Vec<StructuralFinding> {
    let context = RuleContext {
        functions,
        low_use_short_function,
    };
    let rules: [&dyn StructuralRule; 2] = [&TrivialWrapperRule, &LowUseShortFunctionRule];
    let mut findings = Vec::new();
    for rule in rules {
        if RuleContext::supports(rule.metadata().capabilities) {
            findings.extend(rule.check(&context));
        }
    }
    findings
}

impl RuleContext<'_> {
    fn supports(capabilities: &[RuleCapability]) -> bool {
        capabilities
            .iter()
            .all(|capability| Self::supports_capability(*capability))
    }

    const fn supports_capability(capability: RuleCapability) -> bool {
        match capability {
            RuleCapability::FunctionFacts | RuleCapability::CallSites => true,
        }
    }
}

impl StructuralRule for TrivialWrapperRule {
    fn metadata(&self) -> StructuralRuleMetadata {
        TRIVIAL_WRAPPER_METADATA
    }

    fn check(&self, context: &RuleContext<'_>) -> Vec<StructuralFinding> {
        context
            .functions
            .iter()
            .filter_map(trivial_wrapper)
            .collect()
    }
}

impl StructuralRule for LowUseShortFunctionRule {
    fn metadata(&self) -> StructuralRuleMetadata {
        LOW_USE_SHORT_FUNCTION_METADATA
    }

    fn check(&self, context: &RuleContext<'_>) -> Vec<StructuralFinding> {
        if !context.low_use_short_function.enabled {
            return Vec::new();
        }

        context
            .functions
            .iter()
            .filter_map(|function| low_use_short_function(function, context))
            .collect()
    }
}

const fn structural_rule_metadata() -> &'static [StructuralRuleMetadata] {
    &[TRIVIAL_WRAPPER_METADATA, LOW_USE_SHORT_FUNCTION_METADATA]
}

fn trivial_wrapper(function: &Function) -> Option<StructuralFinding> {
    if function.name.starts_with('_') {
        return None;
    }

    let removable = match &function.body_shape {
        BodyShape::IdentityReturn { value } => function.params.iter().any(|param| param == value),
        BodyShape::CallReturn { args, .. } => forwards_only_params(function, args),
        BodyShape::Complex => false,
    };

    removable.then(|| StructuralFinding {
        rule_id: TRIVIAL_WRAPPER_METADATA.id,
        severity: TRIVIAL_WRAPPER_METADATA.severity,
        message: format!("`{}` adds no behavior", function.name),
        file: function.file.clone(),
        start_line: function.start_line,
        end_line: function.end_line,
        subject_name: function.name.clone(),
    })
}

fn forwards_only_params(function: &Function, args: &[String]) -> bool {
    !args.is_empty()
        && args.len() == function.params.len()
        && args
            .iter()
            .all(|arg| function.params.iter().any(|param| param == arg))
}

fn low_use_short_function(
    function: &Function,
    context: &RuleContext<'_>,
) -> Option<StructuralFinding> {
    let settings = context.low_use_short_function;
    if function.sloc > settings.max_function_sloc {
        return None;
    }

    let call_sites = call_sites_for(function, context.functions);
    if call_sites.is_empty() || call_sites.len() > settings.max_call_sites {
        return None;
    }
    if !callers_stay_within_budgets(function, &call_sites, settings) {
        return None;
    }

    Some(StructuralFinding {
        rule_id: LOW_USE_SHORT_FUNCTION_METADATA.id,
        severity: LOW_USE_SHORT_FUNCTION_METADATA.severity,
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

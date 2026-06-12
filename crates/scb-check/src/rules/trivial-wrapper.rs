use crate::model::{BodyShape, Function, StructuralFinding};
use crate::rules::base::{
    AlwaysFixableViolation, Rule, RuleContext, StructuralRuleMetadata, Violation, always_fix_title,
    finding,
};

pub(crate) static RULE: TrivialWrapperRule = TrivialWrapperRule;

#[derive(Debug, Clone, Copy)]
pub(crate) struct TrivialWrapperRule;

#[derive(Debug, Clone, PartialEq, Eq)]
struct TrivialWrapper {
    function_name: String,
}

impl Rule for TrivialWrapperRule {
    fn metadata(&self) -> StructuralRuleMetadata {
        TrivialWrapper::METADATA
    }

    fn check(&self, context: &RuleContext<'_>) -> Vec<StructuralFinding> {
        context
            .functions
            .iter()
            .filter_map(trivial_wrapper)
            .collect()
    }
}

impl Violation for TrivialWrapper {
    const METADATA: StructuralRuleMetadata = StructuralRuleMetadata {
        id: "trivial-wrapper",
        severity: "warning",
        target: "symbol",
        message: "Function adds no behavior.",
    };

    fn message(&self) -> String {
        format!("`{}` adds no behavior", self.function_name)
    }
}

impl AlwaysFixableViolation for TrivialWrapper {
    fn fix_title(&self) -> String {
        format!("Inline or remove `{}`", self.function_name)
    }
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

    removable.then(|| {
        let violation = TrivialWrapper {
            function_name: function.name.clone(),
        };
        finding(
            &violation,
            function.file.clone(),
            function.start_line,
            function.end_line,
            function.name.clone(),
            Some(always_fix_title(&violation)),
        )
    })
}

fn forwards_only_params(function: &Function, args: &[String]) -> bool {
    !args.is_empty()
        && args.len() == function.params.len()
        && args
            .iter()
            .all(|arg| function.params.iter().any(|param| param == arg))
}

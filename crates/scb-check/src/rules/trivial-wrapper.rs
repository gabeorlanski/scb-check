use crate::model::{BodyShape, Function, StructuralFinding};
use crate::rules::base::{Diagnostic, FixAvailability, RuleContext, RuleMetadata, Violation};

pub struct TrivialWrapper {
    function_name: String,
}

impl Violation for TrivialWrapper {
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::Always;
    const METADATA: RuleMetadata = RuleMetadata {
        id: "trivial-wrapper",
        severity: "warning",
        target: "symbol",
        message: "Function adds no behavior.",
    };

    fn message(&self) -> String {
        format!("`{}` adds no behavior", self.function_name)
    }

    fn fix_title(&self) -> Option<String> {
        Some(format!("Inline or remove `{}`", self.function_name))
    }
}

pub fn check(context: &RuleContext<'_>, findings: &mut Vec<StructuralFinding>) {
    findings.extend(context.functions.iter().filter_map(trivial_wrapper));
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
        Diagnostic::new(
            TrivialWrapper {
                function_name: function.name.clone(),
            },
            function.file.clone(),
            function.start_line,
            function.end_line,
            function.name.clone(),
        )
        .into_finding()
    })
}

fn forwards_only_params(function: &Function, args: &[String]) -> bool {
    !args.is_empty()
        && args.len() == function.params.len()
        && args
            .iter()
            .all(|arg| function.params.iter().any(|param| param == arg))
}

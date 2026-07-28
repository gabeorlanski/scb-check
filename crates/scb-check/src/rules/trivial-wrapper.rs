use crate::model::{Function, FunctionBody, SimpleExpr, StructuralFinding, Visibility};
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
    if function.visibility != Visibility::Private
        || function.has_receiver
        || function.has_nontrivial_params
    {
        return None;
    }

    let removable = match &function.body {
        FunctionBody::SimpleReturn(SimpleExpr::Param(_)) => true,
        FunctionBody::SimpleReturn(SimpleExpr::Constant | SimpleExpr::Literal) => {
            function.params.is_empty()
        }
        FunctionBody::SimpleReturn(SimpleExpr::Call(call)) => {
            forwards_only_params(function, &call.args)
        }
        FunctionBody::SimpleReturn(SimpleExpr::Unsupported) | FunctionBody::Complex => false,
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

fn forwards_only_params(function: &Function, args: &[SimpleExpr]) -> bool {
    !args.is_empty()
        && args.len() == function.params.len()
        && args
            .iter()
            .zip(&function.params)
            .all(|(argument, parameter)| {
                matches!(argument, SimpleExpr::Param(name) if name == parameter)
            })
}

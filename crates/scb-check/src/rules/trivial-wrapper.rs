use crate::model::{BodyShape, Function, StructuralFinding};
use crate::rules::base::StructuralRuleMetadata;

pub(crate) const METADATA: StructuralRuleMetadata = StructuralRuleMetadata {
    id: "trivial-wrapper",
    severity: "warning",
    target: "symbol",
    message: "Function adds no behavior.",
};

pub(crate) fn check(functions: &[Function]) -> Vec<StructuralFinding> {
    functions.iter().filter_map(trivial_wrapper).collect()
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
        rule_id: METADATA.id,
        severity: METADATA.severity,
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

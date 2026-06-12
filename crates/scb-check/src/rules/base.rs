#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct StructuralRuleMetadata {
    pub id: &'static str,
    pub severity: &'static str,
    pub target: &'static str,
    pub message: &'static str,
}

pub(crate) fn structural_rule_document(metadata: StructuralRuleMetadata) -> String {
    format!(
        "id: {}\nseverity: {}\ntarget: {}\nkind: structural\nmessage: {}\n",
        metadata.id, metadata.severity, metadata.target, metadata.message
    )
}

pub(crate) mod base;
pub(crate) mod python;
pub(crate) mod rust;

pub(crate) use base::{CommentSpan, FunctionSpan, ParsedSyntax};

use crate::model::Language;

pub(crate) fn parse_syntax(language: Language, source: &str) -> Result<ParsedSyntax, String> {
    match language {
        Language::Python => python::parser::parse_syntax(source),
        Language::Rust => rust::parser::parse_syntax(source),
    }
}

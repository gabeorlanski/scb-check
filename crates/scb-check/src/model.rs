use std::path::PathBuf;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) enum Language {
    Python,
    Rust,
}

impl Language {
    pub(crate) const fn as_str(self) -> &'static str {
        match self {
            Self::Python => "python",
            Self::Rust => "rust",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceFile {
    pub path: PathBuf,
    pub language: Language,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceLines {
    pub file: PathBuf,
    pub lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Function {
    pub file: PathBuf,
    pub language: Language,
    pub name: String,
    pub params: Vec<String>,
    pub start_line: usize,
    pub end_line: usize,
    pub sloc: usize,
    pub cyclomatic: usize,
    pub cognitive: usize,
    pub max_nesting: usize,
    pub calls: Vec<CallSite>,
    pub body_shape: BodyShape,
}

impl Function {
    pub(crate) fn cc_mass(&self) -> f64 {
        self.cyclomatic as f64 * (self.sloc as f64).sqrt()
    }

    pub(crate) fn cog_mass(&self) -> f64 {
        self.cognitive as f64 * (self.sloc as f64).sqrt()
    }

    pub(crate) const fn is_high_cc(&self) -> bool {
        self.cyclomatic > 10
    }

    pub(crate) const fn is_high_cog(&self) -> bool {
        self.cognitive > 10
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CallSite {
    pub name: String,
    pub line: usize,
    pub nesting: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum BodyShape {
    IdentityReturn { value: String },
    CallReturn { callee: String, args: Vec<String> },
    Complex,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CloneBlock {
    pub file: PathBuf,
    pub start_line: usize,
    pub end_line: usize,
    pub group_hash: String,
    pub instance_count: usize,
    pub first_lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AstGrepFinding {
    pub rule_id: String,
    pub severity: String,
    pub message: String,
    pub file: PathBuf,
    pub start_line: usize,
    pub end_line: usize,
    pub start_col: usize,
    pub end_col: usize,
    pub matched_text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct StructuralFinding {
    pub rule_id: &'static str,
    pub severity: &'static str,
    pub message: String,
    pub file: PathBuf,
    pub start_line: usize,
    pub end_line: usize,
    pub subject_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct LanguageSyntaxSummary {
    pub language: Language,
    pub tree_count: usize,
    pub node_count: usize,
}

#[derive(Debug, Clone)]
pub(crate) struct Report {
    pub files_scanned: usize,
    pub total_loc: usize,
    pub verbosity_flagged_loc: usize,
    pub clone_loc: usize,
    pub ast_grep_flagged_loc: usize,
    pub structural_rule_loc: usize,
    pub structural_rule_findings: usize,
    pub total_functions: usize,
    pub high_cc_functions: usize,
    pub high_cog_functions: usize,
    pub total_mass: f64,
    pub high_cc_mass: f64,
    pub total_cog_mass: f64,
    pub high_cog_mass: f64,
    pub syntax_by_language: Vec<LanguageSyntaxSummary>,
    pub clones: Vec<CloneBlock>,
    pub functions: Vec<Function>,
    pub ast_grep_findings: Vec<AstGrepFinding>,
    pub structural_findings: Vec<StructuralFinding>,
    pub source_lines: Vec<SourceLines>,
}

impl Report {
    pub(crate) fn verbosity(&self) -> f64 {
        ratio(self.verbosity_flagged_loc as f64, self.total_loc as f64)
    }

    pub(crate) fn erosion(&self) -> f64 {
        ratio(self.high_cc_mass, self.total_mass)
    }

    pub(crate) fn cog_erosion(&self) -> f64 {
        ratio(self.high_cog_mass, self.total_cog_mass)
    }

    pub(crate) fn syntax_tree_count(&self) -> usize {
        self.syntax_count(|summary| summary.tree_count)
    }

    pub(crate) fn syntax_node_count(&self) -> usize {
        self.syntax_count(|summary| summary.node_count)
    }

    fn syntax_count(&self, count: impl Fn(&LanguageSyntaxSummary) -> usize) -> usize {
        self.syntax_by_language.iter().map(count).sum()
    }

    pub(crate) const fn has_findings(&self) -> bool {
        self.clone_loc > 0
            || !self.clones.is_empty()
            || self.ast_grep_flagged_loc > 0
            || !self.ast_grep_findings.is_empty()
            || !self.structural_findings.is_empty()
            || self.high_cc_functions > 0
            || self.high_cog_functions > 0
    }
}

fn ratio(numerator: f64, denominator: f64) -> f64 {
    if denominator == 0.0 {
        0.0
    } else {
        numerator / denominator
    }
}

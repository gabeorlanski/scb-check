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
    pub(crate) path: PathBuf,
    pub(crate) language: Language,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceLines {
    pub(crate) file: PathBuf,
    pub(crate) lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Function {
    pub(crate) file: PathBuf,
    pub(crate) language: Language,
    pub(crate) name: String,
    pub(crate) params: Vec<String>,
    pub(crate) start_line: usize,
    pub(crate) end_line: usize,
    pub(crate) sloc: usize,
    pub(crate) cyclomatic: usize,
    pub(crate) cognitive: usize,
    pub(crate) max_nesting: usize,
    pub(crate) calls: Vec<CallSite>,
    pub(crate) body_shape: BodyShape,
}

impl Function {
    #[expect(
        clippy::cast_precision_loss,
        reason = "Report mass formulas intentionally use f64 to preserve the existing JSON score contract."
    )]
    pub(crate) fn cc_mass(&self) -> f64 {
        self.cyclomatic as f64 * (self.sloc as f64).sqrt()
    }

    #[expect(
        clippy::cast_precision_loss,
        reason = "Report mass formulas intentionally use f64 to preserve the existing JSON score contract."
    )]
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
    pub(crate) name: String,
    pub(crate) line: usize,
    pub(crate) nesting: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum BodyShape {
    IdentityReturn { value: String },
    CallReturn { callee: String, args: Vec<String> },
    Complex,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CloneBlock {
    pub(crate) file: PathBuf,
    pub(crate) start_line: usize,
    pub(crate) end_line: usize,
    pub(crate) group_hash: String,
    pub(crate) instance_count: usize,
    pub(crate) first_lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AstGrepFinding {
    pub(crate) rule_id: String,
    pub(crate) severity: String,
    pub(crate) message: String,
    pub(crate) file: PathBuf,
    pub(crate) start_line: usize,
    pub(crate) end_line: usize,
    pub(crate) start_col: usize,
    pub(crate) end_col: usize,
    pub(crate) matched_text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct StructuralFinding {
    pub(crate) rule_id: &'static str,
    pub(crate) severity: &'static str,
    pub(crate) message: String,
    pub(crate) fix_title: Option<String>,
    pub(crate) file: PathBuf,
    pub(crate) start_line: usize,
    pub(crate) end_line: usize,
    pub(crate) subject_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct LanguageSyntaxSummary {
    pub(crate) language: Language,
    pub(crate) tree_count: usize,
    pub(crate) node_count: usize,
}

#[derive(Debug, Clone)]
pub(crate) struct Report {
    pub(crate) files_scanned: usize,
    pub(crate) total_loc: usize,
    pub(crate) verbosity_flagged_loc: usize,
    pub(crate) clone_loc: usize,
    pub(crate) ast_grep_flagged_loc: usize,
    pub(crate) structural_rule_loc: usize,
    pub(crate) structural_rule_findings: usize,
    pub(crate) total_functions: usize,
    pub(crate) high_cc_functions: usize,
    pub(crate) high_cog_functions: usize,
    pub(crate) total_mass: f64,
    pub(crate) high_cc_mass: f64,
    pub(crate) total_cog_mass: f64,
    pub(crate) high_cog_mass: f64,
    pub(crate) syntax_by_language: Vec<LanguageSyntaxSummary>,
    pub(crate) clones: Vec<CloneBlock>,
    pub(crate) functions: Vec<Function>,
    pub(crate) ast_grep_findings: Vec<AstGrepFinding>,
    pub(crate) structural_findings: Vec<StructuralFinding>,
    pub(crate) source_lines: Vec<SourceLines>,
}

impl Report {
    #[expect(
        clippy::cast_precision_loss,
        reason = "Verbosity is defined as an f64 JSON ratio over LOC counts and must match prior calculations."
    )]
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

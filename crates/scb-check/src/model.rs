use std::collections::BTreeMap;
use std::path::PathBuf;

use petgraph::Direction;
use petgraph::graph::{DiGraph, NodeIndex};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Language {
    Python,
    Rust,
}

impl Language {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Python => "python",
            Self::Rust => "rust",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Visibility {
    Public,
    Private,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceFile {
    pub path: PathBuf,
    pub language: Language,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceLines {
    pub file: PathBuf,
    pub lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct FunctionId {
    pub file: PathBuf,
    pub qualified_name: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ScopePath {
    pub segments: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ScopeId {
    pub file: PathBuf,
    pub path: ScopePath,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Function {
    pub id: FunctionId,
    pub file: PathBuf,
    pub language: Language,
    pub name: String,
    pub visibility: Visibility,
    pub bare_call_scope: Option<ScopeId>,
    pub visible_bare_call_scopes: Vec<ScopeId>,
    pub has_receiver: bool,
    pub has_nontrivial_params: bool,
    pub params: Vec<String>,
    pub start_line: usize,
    pub end_line: usize,
    pub sloc: usize,
    pub cyclomatic: usize,
    pub cognitive: usize,
    pub max_nesting: usize,
    pub calls: Vec<CallSite>,
    pub body: FunctionBody,
}

impl Function {
    pub fn cc_mass(&self) -> f64 {
        usize_to_f64(self.cyclomatic) * usize_to_f64(self.sloc).sqrt()
    }

    pub fn cog_mass(&self) -> f64 {
        usize_to_f64(self.cognitive) * usize_to_f64(self.sloc).sqrt()
    }

    pub const fn is_high_cc(&self) -> bool {
        self.cyclomatic > 10
    }

    pub const fn is_high_cog(&self) -> bool {
        self.cognitive > 10
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CallSite {
    pub name: String,
    pub target: Option<FunctionId>,
    pub line: usize,
    pub nesting: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImportBinding {
    pub file: PathBuf,
    pub local_name: String,
    pub target_name: String,
    pub target_file_suffixes: Vec<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CallLocation {
    pub caller_index: usize,
    pub call_index: usize,
}

#[derive(Debug, Clone)]
pub struct CallGraph {
    graph: DiGraph<usize, CallLocation>,
    nodes_by_function: BTreeMap<FunctionId, NodeIndex>,
}

impl CallGraph {
    pub fn from_functions(functions: &[Function]) -> Self {
        let mut graph = DiGraph::new();
        let nodes_by_function: BTreeMap<FunctionId, NodeIndex> = functions
            .iter()
            .enumerate()
            .map(|(index, function)| (function.id.clone(), graph.add_node(index)))
            .collect();

        for (caller_index, function) in functions.iter().enumerate() {
            for (call_index, call) in function.calls.iter().enumerate() {
                if let Some(target_node) = call
                    .target
                    .as_ref()
                    .and_then(|target| nodes_by_function.get(target))
                {
                    graph.add_edge(
                        nodes_by_function[&function.id],
                        *target_node,
                        CallLocation {
                            caller_index,
                            call_index,
                        },
                    );
                }
            }
        }
        Self {
            graph,
            nodes_by_function,
        }
    }

    pub fn incoming_to<'functions>(
        &self,
        functions: &'functions [Function],
        target: &FunctionId,
    ) -> Vec<ResolvedCall<'functions>> {
        let Some(target_node) = self.nodes_by_function.get(target) else {
            return Vec::new();
        };

        self.graph
            .edges_directed(*target_node, Direction::Incoming)
            .filter_map(|edge| {
                let location = edge.weight();
                let caller = functions.get(location.caller_index)?;
                let call = caller.calls.get(location.call_index)?;
                Some(ResolvedCall { caller, call })
            })
            .collect()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResolvedCall<'functions> {
    pub caller: &'functions Function,
    pub call: &'functions CallSite,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FunctionBody {
    SimpleReturn(SimpleExpr),
    Complex,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SimpleExpr {
    Param(String),
    Constant,
    Literal,
    Unsupported,
    Call(SimpleCall),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SimpleCall {
    pub callee: String,
    pub args: Vec<SimpleExpr>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloneBlock {
    pub file: PathBuf,
    pub start_line: usize,
    pub end_line: usize,
    pub sloc: usize,
    pub group_hash: String,
    pub instance_count: usize,
    pub first_lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AstGrepFinding {
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
pub struct StructuralFinding {
    pub rule_id: &'static str,
    pub severity: &'static str,
    pub message: String,
    pub fix_title: Option<String>,
    pub file: PathBuf,
    pub start_line: usize,
    pub end_line: usize,
    pub subject_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LanguageSyntaxSummary {
    pub language: Language,
    pub tree_count: usize,
    pub node_count: usize,
}

#[derive(Debug, Clone)]
pub struct Report {
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
    pub fn verbosity(&self) -> f64 {
        ratio(
            usize_to_f64(self.verbosity_flagged_loc),
            usize_to_f64(self.total_loc),
        )
    }

    pub fn erosion(&self) -> f64 {
        ratio(self.high_cc_mass, self.total_mass)
    }

    pub fn cog_erosion(&self) -> f64 {
        ratio(self.high_cog_mass, self.total_cog_mass)
    }

    pub fn syntax_tree_count(&self) -> usize {
        self.syntax_count(|summary| summary.tree_count)
    }

    pub fn syntax_node_count(&self) -> usize {
        self.syntax_count(|summary| summary.node_count)
    }

    fn syntax_count(&self, count: impl Fn(&LanguageSyntaxSummary) -> usize) -> usize {
        self.syntax_by_language.iter().map(count).sum()
    }

    pub const fn has_findings(&self) -> bool {
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

fn usize_to_f64(value: usize) -> f64 {
    value
        .to_string()
        .parse::<f64>()
        .expect("usize decimal representation should parse as f64")
}

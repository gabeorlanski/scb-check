use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::astgrep::AstGrepCatalog;
use crate::clones::{CloneCandidate, detect_clones, function_clone_candidate};
use crate::config::LowUseShortFunctionSettings;
use crate::directives::{
    BoundaryDirective, IgnoreDirective, filter_ast_grep_findings, filter_structural_findings,
    parse_source_directives,
};
use crate::languages::{ast_grep_language, function_lines, lower_function, parse_syntax_at_path};
use crate::model::{
    AstGrepFinding, CallGraph, CallSite, CloneBlock, Function, FunctionId, ImportBinding, Language,
    LanguageSyntaxSummary, Report, SourceFile, SourceLines, StructuralFinding,
};
use crate::rules::{run_structural_rules, structural_rule_ids};

#[derive(Debug)]
struct ParsedFile {
    path: PathBuf,
    language: Language,
    sloc_lines: BTreeSet<usize>,
    functions: Vec<Function>,
    clone_candidates: Vec<CloneCandidate>,
    ast_grep_findings: Vec<AstGrepFinding>,
    ignore_directives: Vec<IgnoreDirective>,
    boundary_directives: Vec<BoundaryDirective>,
    imports: Vec<ImportBinding>,
    node_count: usize,
    source_lines: SourceLines,
}

#[derive(Debug)]
struct ProjectFacts {
    functions: Vec<Function>,
    clone_candidates: Vec<CloneCandidate>,
    ast_grep_findings: Vec<AstGrepFinding>,
    ignore_directives: Vec<IgnoreDirective>,
    boundary_directives: Vec<BoundaryDirective>,
    imports: Vec<ImportBinding>,
    total_loc: usize,
    source_lines: Vec<SourceLines>,
    syntax_counts: BTreeMap<Language, (usize, usize)>,
}

#[derive(Debug)]
struct LineSummary {
    verbosity_flagged: usize,
    clone: usize,
    ast_grep_flagged: usize,
    structural_rule: usize,
}

#[derive(Debug)]
struct FunctionSummary {
    high_cc_functions: usize,
    high_cog_functions: usize,
    total_mass: f64,
    high_cc_mass: f64,
    total_cog_mass: f64,
    high_cog_mass: f64,
}

#[derive(Debug)]
enum ParseFileError {
    Directive(String),
    Parse(String),
}

pub fn analyze(
    files: &[SourceFile],
    disable_sg: bool,
    include_all: bool,
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Result<Report, String> {
    let ast_grep_catalog = AstGrepCatalog::load()?;
    let valid_rule_ids = valid_rule_ids(&ast_grep_catalog)?;
    let mut parsed_files = parse_files(
        files,
        disable_sg,
        include_all,
        &valid_rule_ids,
        &ast_grep_catalog,
    )?;
    let files_scanned = parsed_files.len();
    let mut project = collect_project_facts(&mut parsed_files);
    resolve_project_call_sites(&mut project.functions, &project.imports);
    let call_graph = CallGraph::from_functions(&project.functions);
    let clones = detect_clones(project.clone_candidates);
    let mut ast_grep_findings = project.ast_grep_findings;
    let mut structural_findings =
        run_structural_rules(&project.functions, &call_graph, low_use_short_function);
    ast_grep_findings = filter_ast_grep_findings(
        ast_grep_findings,
        &project.ignore_directives,
        &project.boundary_directives,
        &project.functions,
        include_all,
    )?;
    if !include_all {
        ast_grep_findings = apply_count_thresholds(ast_grep_findings, &ast_grep_catalog);
        structural_findings =
            filter_structural_findings(structural_findings, &project.ignore_directives);
    }
    let line_summary = line_summary(
        &clones,
        &ast_grep_findings,
        &structural_findings,
        &parsed_files,
    );
    let function_summary = function_summary(&project.functions);

    Ok(Report {
        files_scanned,
        total_loc: project.total_loc,
        verbosity_flagged_loc: line_summary.verbosity_flagged,
        clone_loc: line_summary.clone,
        ast_grep_flagged_loc: line_summary.ast_grep_flagged,
        structural_rule_loc: line_summary.structural_rule,
        structural_rule_findings: structural_findings.len(),
        total_functions: project.functions.len(),
        high_cc_functions: function_summary.high_cc_functions,
        high_cog_functions: function_summary.high_cog_functions,
        total_mass: function_summary.total_mass,
        high_cc_mass: function_summary.high_cc_mass,
        total_cog_mass: function_summary.total_cog_mass,
        high_cog_mass: function_summary.high_cog_mass,
        syntax_by_language: project
            .syntax_counts
            .into_iter()
            .map(
                |(language, (tree_count, node_count))| LanguageSyntaxSummary {
                    language,
                    tree_count,
                    node_count,
                },
            )
            .collect(),
        clones,
        functions: project.functions,
        ast_grep_findings,
        structural_findings,
        source_lines: project.source_lines,
    })
}

fn sorted_scored_functions(functions: &[Function]) -> Vec<&Function> {
    let mut sorted: Vec<&Function> = functions.iter().collect();
    sorted.sort_by(|left, right| {
        (
            left.file.to_string_lossy(),
            left.start_line,
            left.name.as_str(),
        )
            .cmp(&(
                right.file.to_string_lossy(),
                right.start_line,
                right.name.as_str(),
            ))
    });
    sorted
}

fn line_summary(
    clones: &[CloneBlock],
    ast_grep_findings: &[AstGrepFinding],
    structural_findings: &[StructuralFinding],
    parsed_files: &[ParsedFile],
) -> LineSummary {
    let clone_lines = finding_item_lines(clones, parsed_files);
    let ast_grep_lines = finding_item_lines(ast_grep_findings, parsed_files);
    let structural_lines = finding_item_lines(structural_findings, parsed_files);
    let clone_loc = clone_lines.len();
    let ast_grep_flagged_loc = ast_grep_lines.len();
    let structural_rule_loc = structural_lines.len();
    let mut verbosity_lines = clone_lines;
    verbosity_lines.extend(ast_grep_lines);
    verbosity_lines.extend(structural_lines);

    LineSummary {
        verbosity_flagged: verbosity_lines.len(),
        clone: clone_loc,
        ast_grep_flagged: ast_grep_flagged_loc,
        structural_rule: structural_rule_loc,
    }
}

fn resolve_project_call_sites(functions: &mut [Function], imports: &[ImportBinding]) {
    let targets: Vec<Vec<Option<FunctionId>>> = functions
        .iter()
        .map(|caller| {
            caller
                .calls
                .iter()
                .map(|call| resolve_bare_call(caller, call, functions, imports))
                .collect()
        })
        .collect();

    for (function, resolved_targets) in functions.iter_mut().zip(targets) {
        for (call, target) in function.calls.iter_mut().zip(resolved_targets) {
            call.target = target;
        }
    }
}

fn resolve_bare_call(
    caller: &Function,
    call: &CallSite,
    functions: &[Function],
    imports: &[ImportBinding],
) -> Option<FunctionId> {
    for scope in &caller.visible_bare_call_scopes {
        let mut matches = functions.iter().filter(|function| {
            function.file == caller.file
                && function.name == call.name
                && function
                    .bare_call_scope
                    .as_ref()
                    .is_some_and(|target_scope| target_scope == scope)
        });
        let Some(function) = matches.next() else {
            continue;
        };
        if matches.next().is_none() {
            return Some(function.id.clone());
        }
        return None;
    }

    let mut matches = imports
        .iter()
        .filter(|binding| binding.file == caller.file)
        .filter(|binding| binding.local_name == call.name)
        .flat_map(|binding| {
            functions.iter().filter(move |function| {
                function.name == binding.target_name
                    && function
                        .bare_call_scope
                        .as_ref()
                        .is_some_and(|scope| scope.path.segments.is_empty())
                    && binding
                        .target_file_suffixes
                        .iter()
                        .any(|suffix| function.file.ends_with(suffix))
            })
        });
    let target = matches.next()?;
    matches.next().is_none().then(|| target.id.clone())
}

fn function_summary(functions: &[Function]) -> FunctionSummary {
    let sorted_functions = sorted_scored_functions(functions);
    let high_cc_functions = sorted_functions
        .iter()
        .filter(|function| function.is_high_cc())
        .count();
    let high_cog_functions = sorted_functions
        .iter()
        .filter(|function| function.is_high_cog())
        .count();
    let high_cc_mass = sorted_functions
        .iter()
        .filter(|function| function.is_high_cc())
        .map(|function| function.cc_mass());
    let high_cog_mass = sorted_functions
        .iter()
        .filter(|function| function.is_high_cog())
        .map(|function| function.cog_mass());

    FunctionSummary {
        high_cc_functions,
        high_cog_functions,
        total_mass: sum_mass(sorted_functions.iter().map(|function| function.cc_mass())),
        high_cc_mass: sum_mass(high_cc_mass),
        total_cog_mass: sum_mass(sorted_functions.iter().map(|function| function.cog_mass())),
        high_cog_mass: sum_mass(high_cog_mass),
    }
}

fn sum_mass(values: impl Iterator<Item = f64>) -> f64 {
    let mut total = 0.0_f64;
    let mut compensation = 0.0_f64;
    for value in values {
        let next = total + value;
        if total.abs() >= value.abs() {
            compensation += (total - next) + value;
        } else {
            compensation += (value - next) + total;
        }
        total = next;
    }
    total + compensation
}

fn parse_files(
    files: &[SourceFile],
    disable_sg: bool,
    include_all: bool,
    valid_rule_ids: &BTreeSet<String>,
    ast_grep_catalog: &AstGrepCatalog,
) -> Result<Vec<ParsedFile>, String> {
    let mut parsed_files = Vec::new();
    for file in files {
        match parse_file(
            file,
            disable_sg,
            include_all,
            valid_rule_ids,
            ast_grep_catalog,
        ) {
            Ok(parsed) => parsed_files.push(parsed),
            Err(ParseFileError::Directive(message)) => return Err(message),
            Err(ParseFileError::Parse(message)) => {
                eprintln!("failed to parse file: {message}");
            }
        }
    }
    Ok(parsed_files)
}

fn collect_project_facts(parsed_files: &mut [ParsedFile]) -> ProjectFacts {
    let mut functions = Vec::new();
    let mut clone_candidates = Vec::new();
    let mut ast_grep_findings = Vec::new();
    let mut ignore_directives = Vec::new();
    let mut boundary_directives = Vec::new();
    let mut imports = Vec::new();
    let mut total_loc = 0;
    let mut source_lines = Vec::new();
    let mut syntax_counts: BTreeMap<Language, (usize, usize)> = BTreeMap::new();
    for parsed in parsed_files {
        total_loc += parsed.sloc_lines.len();
        functions.append(&mut parsed.functions);
        clone_candidates.append(&mut parsed.clone_candidates);
        ast_grep_findings.append(&mut parsed.ast_grep_findings);
        ignore_directives.append(&mut parsed.ignore_directives);
        boundary_directives.append(&mut parsed.boundary_directives);
        imports.append(&mut parsed.imports);
        source_lines.push(std::mem::replace(
            &mut parsed.source_lines,
            SourceLines {
                file: parsed.path.clone(),
                lines: Vec::new(),
            },
        ));
        let entry = syntax_counts.entry(parsed.language).or_insert((0, 0));
        entry.0 += 1;
        entry.1 += parsed.node_count;
    }

    ProjectFacts {
        functions,
        clone_candidates,
        ast_grep_findings,
        ignore_directives,
        boundary_directives,
        imports,
        total_loc,
        source_lines,
        syntax_counts,
    }
}

fn parse_file(
    file: &SourceFile,
    disable_sg: bool,
    include_all: bool,
    valid_rule_ids: &BTreeSet<String>,
    ast_grep_catalog: &AstGrepCatalog,
) -> Result<ParsedFile, ParseFileError> {
    let source = fs::read_to_string(&file.path)
        .map_err(|error| ParseFileError::Parse(format!("{}: {error}", file.path.display())))?;
    let lines: Vec<&str> = source.lines().collect();
    let syntax = parse_syntax_at_path(file.language, &file.path, &source)
        .map_err(|error| ParseFileError::Parse(format!("{}: {error}", file.path.display())))?;
    let sloc_lines = syntax.sloc_lines.clone();
    let parsed_directives = parse_source_directives(
        file.language,
        &file.path,
        &source,
        &syntax.comments,
        valid_rule_ids,
    )
    .map_err(ParseFileError::Directive)?;
    let functions: Vec<Function> = syntax
        .functions
        .iter()
        .map(|span| lower_function(file.language, &file.path, span, &lines, &sloc_lines))
        .collect();
    let clone_candidates = functions
        .iter()
        .zip(&syntax.functions)
        .filter_map(|(function, span)| {
            function_clone_candidate(
                function,
                &span.clone_fingerprint,
                function_lines(span, &lines),
                &sloc_lines,
            )
        })
        .collect();
    let ast_grep_findings = if disable_sg {
        Vec::new()
    } else if let Some(language) = ast_grep_language(file.language) {
        ast_grep_catalog.run_rules(language, &file.path, &source, include_all)
    } else {
        Vec::new()
    };

    Ok(ParsedFile {
        path: file.path.clone(),
        language: file.language,
        sloc_lines,
        functions,
        clone_candidates,
        ast_grep_findings,
        ignore_directives: parsed_directives.ignores,
        boundary_directives: parsed_directives.boundaries,
        imports: syntax.imports,
        node_count: syntax.node_count,
        source_lines: SourceLines {
            file: file.path.clone(),
            lines: lines.iter().map(|line| (*line).to_string()).collect(),
        },
    })
}

fn valid_rule_ids(ast_grep_catalog: &AstGrepCatalog) -> Result<BTreeSet<String>, String> {
    let ast_ids: BTreeSet<String> = ast_grep_catalog.rule_ids().into_iter().collect();
    let structural_ids: BTreeSet<String> = structural_rule_ids()
        .into_iter()
        .map(ToString::to_string)
        .collect();
    validate_unique_rule_ids(&ast_ids, &structural_ids)?;
    Ok(ast_ids.union(&structural_ids).cloned().collect())
}

fn validate_unique_rule_ids(
    ast_ids: &BTreeSet<String>,
    structural_ids: &BTreeSet<String>,
) -> Result<(), String> {
    if let Some(duplicate) = ast_ids.intersection(structural_ids).next() {
        return Err(format!("duplicate rule id: {duplicate}"));
    }
    Ok(())
}

fn apply_count_thresholds(
    findings: Vec<AstGrepFinding>,
    ast_grep_catalog: &AstGrepCatalog,
) -> Vec<AstGrepFinding> {
    apply_threshold_map(findings, &ast_grep_catalog.thresholds())
}

fn apply_threshold_map(
    findings: Vec<AstGrepFinding>,
    thresholds: &BTreeMap<String, usize>,
) -> Vec<AstGrepFinding> {
    if thresholds.is_empty() {
        return findings;
    }

    let mut counts: BTreeMap<(String, PathBuf), usize> = BTreeMap::new();
    for finding in &findings {
        if thresholds.contains_key(&finding.rule_id) {
            *counts
                .entry((finding.rule_id.clone(), finding.file.clone()))
                .or_insert(0) += 1;
        }
    }

    findings
        .into_iter()
        .filter(|finding| {
            let Some(threshold) = thresholds.get(&finding.rule_id) else {
                return true;
            };
            counts
                .get(&(finding.rule_id.clone(), finding.file.clone()))
                .is_some_and(|count| count >= threshold)
        })
        .collect()
}

trait FindingRange {
    fn file(&self) -> &PathBuf;
    fn start_line(&self) -> usize;
    fn end_line(&self) -> usize;
}

impl FindingRange for StructuralFinding {
    fn file(&self) -> &PathBuf {
        &self.file
    }

    fn start_line(&self) -> usize {
        self.start_line
    }

    fn end_line(&self) -> usize {
        self.end_line
    }
}

impl FindingRange for AstGrepFinding {
    fn file(&self) -> &PathBuf {
        &self.file
    }

    fn start_line(&self) -> usize {
        self.start_line
    }

    fn end_line(&self) -> usize {
        self.end_line
    }
}

impl FindingRange for crate::model::CloneBlock {
    fn file(&self) -> &PathBuf {
        &self.file
    }

    fn start_line(&self) -> usize {
        self.start_line
    }

    fn end_line(&self) -> usize {
        self.end_line
    }
}

fn finding_item_lines(
    findings: &[impl FindingRange],
    parsed_files: &[ParsedFile],
) -> BTreeSet<(PathBuf, usize)> {
    finding_lines(
        parsed_files,
        findings
            .iter()
            .map(|finding| (finding.file(), finding.start_line(), finding.end_line())),
    )
}

fn finding_lines<'a>(
    parsed_files: &'a [ParsedFile],
    findings: impl Iterator<Item = (&'a PathBuf, usize, usize)>,
) -> BTreeSet<(PathBuf, usize)> {
    let sloc_by_file: BTreeMap<&Path, &BTreeSet<usize>> = parsed_files
        .iter()
        .map(|parsed| (parsed.path.as_path(), &parsed.sloc_lines))
        .collect();
    findings
        .flat_map(|(file, start_line, end_line)| {
            sloc_lines_for_range(file, start_line, end_line, &sloc_by_file)
        })
        .collect()
}

fn sloc_lines_for_range(
    file: &Path,
    start_line: usize,
    end_line: usize,
    sloc_by_file: &BTreeMap<&Path, &BTreeSet<usize>>,
) -> Vec<(PathBuf, usize)> {
    let Some(sloc_lines) = sloc_by_file.get(file) else {
        return Vec::new();
    };
    (start_line..=end_line)
        .filter(|line| sloc_lines.contains(line))
        .map(|line| (file.to_path_buf(), line))
        .collect()
}

#[cfg(test)]
mod tests {
    use std::collections::{BTreeMap, BTreeSet};
    use std::path::PathBuf;

    use serde_json::json;

    use super::{apply_threshold_map, validate_unique_rule_ids};
    use crate::model::AstGrepFinding;
    use crate::render::render_json;
    use crate::test_support::{analyze_dir, test_dir, workspace_root, write};

    #[test]
    fn reports_python_and_rust_json_contract() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
            r"
def identity(value):
    return value

def branch(value):
    if value > 0:
        return value
    return 0
",
        );
        write(
            &root.join("sample.rs"),
            r"
fn identity(value: i32) -> i32 {
    value
}

fn branch(value: i32) -> i32 {
    if value > 0 {
        return value;
    }
    0
}
",
        );

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");
        let rendered = render_json(&report);

        for key in [
            "verbosity",
            "erosion",
            "cog_erosion",
            "files_scanned",
            "total_loc",
            "verbosity_flagged_loc",
            "clone_loc",
            "ast_grep_flagged_loc",
            "structural_rule_loc",
            "structural_rule_findings",
            "total_functions",
            "high_cc_functions",
            "high_cog_functions",
            "total_mass",
            "high_cc_mass",
            "total_cog_mass",
            "high_cog_mass",
            "syntax_tree_count",
            "syntax_node_count",
            "syntax_by_language",
        ] {
            assert!(
                rendered.contains(&format!("\"{key}\"")),
                "missing key {key}"
            );
        }
        assert!(report.has_findings());
        assert!(rendered.contains("\"files_scanned\":2"));
        assert!(rendered.contains("\"total_functions\":4"));
        assert!(rendered.contains("\"python\""));
        assert!(rendered.contains("\"rust\""));
        assert!(!rendered.contains("-0"));
    }

    #[test]
    fn cutover_fixture_json_reports_match_expected_values() {
        for case in cutover_json_cases() {
            let fixture = workspace_root()
                .join("tests/fixtures/rust_cutover_parity")
                .join(case.name);
            let report = analyze_dir(
                &fixture,
                case.disable_sg,
                false,
                Some(&fixture.join("scb-check.toml")),
            )
            .expect("analysis should succeed");
            let actual: serde_json::Value =
                serde_json::from_str(&render_json(&report)).expect("report should be json");

            assert_eq!(report.has_findings(), case.has_findings, "{}", case.name);
            assert_eq!(actual, case.expected, "{}", case.name);
        }
    }

    #[test]
    fn duplicate_ast_grep_and_structural_rule_ids_are_usage_errors() {
        let ast_ids = BTreeSet::from(["trivial-wrapper".to_string()]);
        let structural_ids = BTreeSet::from(["trivial-wrapper".to_string()]);

        let error =
            validate_unique_rule_ids(&ast_ids, &structural_ids).expect_err("ids should collide");

        assert_eq!(error, "duplicate rule id: trivial-wrapper");
    }

    #[test]
    fn ast_grep_min_file_count_thresholds_filter_sparse_files() {
        let sparse = PathBuf::from("sparse.py");
        let dense = PathBuf::from("dense.py");
        let findings = vec![
            ast_finding("env-threshold-pass", &sparse, 1),
            ast_finding("env-threshold-pass", &dense, 1),
            ast_finding("env-threshold-pass", &dense, 4),
            ast_finding("other-rule", &sparse, 2),
        ];
        let thresholds = BTreeMap::from([("env-threshold-pass".to_string(), 2)]);

        let kept = apply_threshold_map(findings, &thresholds);

        assert_eq!(kept.len(), 3);
        assert!(
            kept.iter()
                .all(|finding| finding.rule_id == "other-rule" || finding.file == dense)
        );
    }

    fn ast_finding(rule_id: &str, file: &std::path::Path, line: usize) -> AstGrepFinding {
        AstGrepFinding {
            rule_id: rule_id.to_string(),
            severity: "warning".to_string(),
            message: "message".to_string(),
            file: file.to_path_buf(),
            start_line: line,
            end_line: line,
            start_col: 0,
            end_col: 1,
            matched_text: "pass".to_string(),
        }
    }

    struct CutoverJsonCase {
        name: &'static str,
        disable_sg: bool,
        has_findings: bool,
        expected: serde_json::Value,
    }

    fn cutover_json_cases() -> Vec<CutoverJsonCase> {
        vec![
            scoreless_mixed_case(),
            python_wrapper_case(),
            python_clone_case(),
            python_low_use_case(),
            rust_clone_case(),
            python_astgrep_case(),
        ]
    }

    fn scoreless_mixed_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "scoreless_mixed",
            disable_sg: true,
            has_findings: false,
            expected: json!({
                "ast_grep_flagged_loc": 0,
                "clone_loc": 0,
                "cog_erosion": 0.0,
                "erosion": 0.0,
                "files_scanned": 2,
                "high_cc_functions": 0,
                "high_cc_mass": 0.0,
                "high_cog_functions": 0,
                "high_cog_mass": 0.0,
                "structural_rule_findings": 0,
                "structural_rule_loc": 0,
                "syntax_by_language": {
                    "python": {"node_count": 6, "tree_count": 1},
                    "rust": {"node_count": 20, "tree_count": 1},
                },
                "syntax_node_count": 26,
                "syntax_tree_count": 2,
                "total_cog_mass": 0.0,
                "total_functions": 1,
                "total_loc": 3,
                "total_mass": std::f64::consts::SQRT_2,
                "verbosity": 0.0,
                "verbosity_flagged_loc": 0,
            }),
        }
    }

    fn python_wrapper_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "python_wrapper",
            disable_sg: true,
            has_findings: true,
            expected: json!({
                "ast_grep_flagged_loc": 0,
                "clone_loc": 0,
                "cog_erosion": 0.0,
                "erosion": 0.0,
                "files_scanned": 1,
                "high_cc_functions": 0,
                "high_cc_mass": 0.0,
                "high_cog_functions": 0,
                "high_cog_mass": 0.0,
                "structural_rule_findings": 1,
                "structural_rule_loc": 2,
                "syntax_by_language": {"python": {"node_count": 13, "tree_count": 1}},
                "syntax_node_count": 13,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 1,
                "total_loc": 2,
                "total_mass": std::f64::consts::SQRT_2,
                "verbosity": 1.0,
                "verbosity_flagged_loc": 2,
            }),
        }
    }

    fn python_clone_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "python_clone",
            disable_sg: true,
            has_findings: true,
            expected: clone_case("python", 57),
        }
    }

    fn rust_clone_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "rust_clone",
            disable_sg: true,
            has_findings: true,
            expected: clone_case("rust", 69),
        }
    }

    fn clone_case(language: &str, node_count: usize) -> serde_json::Value {
        json!({
            "ast_grep_flagged_loc": 0,
            "clone_loc": 8,
            "cog_erosion": 0.0,
            "erosion": 0.0,
            "files_scanned": 1,
            "high_cc_functions": 0,
            "high_cc_mass": 0.0,
            "high_cog_functions": 0,
            "high_cog_mass": 0.0,
            "structural_rule_findings": 0,
            "structural_rule_loc": 0,
            "syntax_by_language": {language: {"node_count": node_count, "tree_count": 1}},
            "syntax_node_count": node_count,
            "syntax_tree_count": 1,
            "total_cog_mass": 0.0,
            "total_functions": 2,
            "total_loc": 8,
            "total_mass": 4.0,
            "verbosity": 1.0,
            "verbosity_flagged_loc": 8,
        })
    }

    fn python_low_use_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "python_low_use",
            disable_sg: true,
            has_findings: true,
            expected: json!({
                "ast_grep_flagged_loc": 0,
                "clone_loc": 0,
                "cog_erosion": 0.0,
                "erosion": 0.0,
                "files_scanned": 1,
                "high_cc_functions": 0,
                "high_cc_mass": 0.0,
                "high_cog_functions": 0,
                "high_cog_mass": 0.0,
                "structural_rule_findings": 1,
                "structural_rule_loc": 3,
                "syntax_by_language": {"python": {"node_count": 42, "tree_count": 1}},
                "syntax_node_count": 42,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 2,
                "total_loc": 5,
                "total_mass": 3.146_264_369_941_973,
                "verbosity": 0.6,
                "verbosity_flagged_loc": 3,
            }),
        }
    }

    fn python_astgrep_case() -> CutoverJsonCase {
        CutoverJsonCase {
            name: "python_astgrep",
            disable_sg: false,
            has_findings: true,
            expected: json!({
                "ast_grep_flagged_loc": 2,
                "clone_loc": 0,
                "cog_erosion": 0.0,
                "erosion": 0.0,
                "files_scanned": 1,
                "high_cc_functions": 0,
                "high_cc_mass": 0.0,
                "high_cog_functions": 0,
                "high_cog_mass": 0.0,
                "structural_rule_findings": 0,
                "structural_rule_loc": 0,
                "syntax_by_language": {"python": {"node_count": 38, "tree_count": 1}},
                "syntax_node_count": 38,
                "syntax_tree_count": 1,
                "total_cog_mass": 1.732_050_807_568_877_2,
                "total_functions": 1,
                "total_loc": 3,
                "total_mass": 3.464_101_615_137_754_4,
                "verbosity": 0.666_666_666_666_666_6,
                "verbosity_flagged_loc": 2,
            }),
        }
    }
}

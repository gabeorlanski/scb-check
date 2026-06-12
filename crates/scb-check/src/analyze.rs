use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::astgrep::{ast_grep_rule_ids, ast_grep_thresholds, run_python_rules};
use crate::clones::{CloneCandidate, detect_clones, function_clone_candidate};
use crate::config::LowUseShortFunctionSettings;
use crate::directives::{
    BoundaryDirective, IgnoreDirective, ParsedDirectives, filter_ast_grep_findings,
    filter_structural_findings, parse_source_directives,
};
use crate::facts::{build_function, function_lines};
use crate::model::{
    AstGrepFinding, Function, Language, LanguageSyntaxSummary, Report, SourceFile, SourceLines,
    StructuralFinding,
};
use crate::parser::parse_syntax;
use crate::rules::{run_structural_rules, structural_rule_ids};

#[derive(Debug, Clone)]
struct ParsedFile {
    path: PathBuf,
    language: Language,
    sloc_lines: BTreeSet<usize>,
    functions: Vec<Function>,
    clone_candidates: Vec<CloneCandidate>,
    ast_grep_findings: Vec<AstGrepFinding>,
    ignore_directives: Vec<IgnoreDirective>,
    boundary_directives: Vec<BoundaryDirective>,
    node_count: usize,
    source_lines: SourceLines,
}

#[derive(Debug, Clone)]
struct ProjectFacts {
    functions: Vec<Function>,
    clone_candidates: Vec<CloneCandidate>,
    ast_grep_findings: Vec<AstGrepFinding>,
    ignore_directives: Vec<IgnoreDirective>,
    boundary_directives: Vec<BoundaryDirective>,
    total_loc: usize,
    source_lines: Vec<SourceLines>,
    syntax_counts: BTreeMap<Language, (usize, usize)>,
}

pub(crate) fn analyze(
    files: &[SourceFile],
    disable_sg: bool,
    include_all: bool,
    low_use_short_function: &LowUseShortFunctionSettings,
) -> Result<Report, String> {
    let valid_rule_ids = valid_rule_ids()?;
    let parsed_files = parse_files(files, disable_sg, include_all, &valid_rule_ids)?;
    let project = collect_project_facts(&parsed_files);
    let clones = detect_clones(project.clone_candidates.clone());
    let clone_lines = finding_item_lines(&clones, &parsed_files);
    let mut ast_grep_findings = project.ast_grep_findings;
    let mut structural_findings = run_structural_rules(&project.functions, low_use_short_function);
    if !include_all {
        ast_grep_findings = filter_ast_grep_findings(
            ast_grep_findings,
            &project.ignore_directives,
            &project.boundary_directives,
            &project.functions,
        )?;
        ast_grep_findings = apply_count_thresholds(ast_grep_findings)?;
        structural_findings =
            filter_structural_findings(structural_findings, &project.ignore_directives);
    }
    let structural_lines = finding_item_lines(&structural_findings, &parsed_files);
    let ast_grep_lines = finding_item_lines(&ast_grep_findings, &parsed_files);
    let ast_grep_flagged_loc = ast_grep_lines.len();
    let clone_loc = clone_lines.len();
    let mut verbosity_lines = clone_lines;
    verbosity_lines.extend(ast_grep_lines.iter().cloned());
    verbosity_lines.extend(structural_lines.iter().cloned());
    let verbosity_flagged_loc = verbosity_lines.len();

    let sorted_functions = sorted_scored_functions(&project.functions);
    let high_cc_functions = sorted_functions
        .iter()
        .filter(|function| function.is_high_cc())
        .count();
    let high_cog_functions = sorted_functions
        .iter()
        .filter(|function| function.is_high_cog())
        .count();
    let total_mass = sum_mass(sorted_functions.iter().map(|function| function.cc_mass()));
    let high_cc_mass = sorted_functions
        .iter()
        .filter(|function| function.is_high_cc())
        .map(|function| function.cc_mass());
    let high_cc_mass = sum_mass(high_cc_mass);
    let total_cog_mass = sum_mass(sorted_functions.iter().map(|function| function.cog_mass()));
    let high_cog_mass = sorted_functions
        .iter()
        .filter(|function| function.is_high_cog())
        .map(|function| function.cog_mass());
    let high_cog_mass = sum_mass(high_cog_mass);

    Ok(Report {
        files_scanned: parsed_files.len(),
        total_loc: project.total_loc,
        verbosity_flagged_loc,
        clone_loc,
        ast_grep_flagged_loc,
        structural_rule_loc: structural_lines.len(),
        structural_rule_findings: structural_findings.len(),
        total_functions: project.functions.len(),
        high_cc_functions,
        high_cog_functions,
        total_mass,
        high_cc_mass,
        total_cog_mass,
        high_cog_mass,
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
) -> Result<Vec<ParsedFile>, String> {
    let mut parsed_files = Vec::new();
    for file in files {
        match parse_file(file, disable_sg, include_all, valid_rule_ids) {
            Ok(parsed) => parsed_files.push(parsed),
            Err(message) if message.starts_with("directive error: ") => {
                return Err(message.trim_start_matches("directive error: ").to_string());
            }
            Err(message) => {
                eprintln!("failed to parse file: {message}");
            }
        }
    }
    Ok(parsed_files)
}

fn collect_project_facts(parsed_files: &[ParsedFile]) -> ProjectFacts {
    let mut functions = Vec::new();
    let mut clone_candidates = Vec::new();
    let mut ast_grep_findings = Vec::new();
    let mut ignore_directives = Vec::new();
    let mut boundary_directives = Vec::new();
    let mut total_loc = 0;
    let mut source_lines = Vec::new();
    let mut syntax_counts: BTreeMap<Language, (usize, usize)> = BTreeMap::new();
    for parsed in parsed_files {
        total_loc += parsed.sloc_lines.len();
        functions.extend(parsed.functions.clone());
        clone_candidates.extend(parsed.clone_candidates.clone());
        ast_grep_findings.extend(parsed.ast_grep_findings.clone());
        ignore_directives.extend(parsed.ignore_directives.clone());
        boundary_directives.extend(parsed.boundary_directives.clone());
        source_lines.push(parsed.source_lines.clone());
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
) -> Result<ParsedFile, String> {
    let source =
        read_source(&file.path).map_err(|error| format!("{}: {error}", file.path.display()))?;
    let lines: Vec<&str> = source.lines().collect();
    let syntax = parse_syntax(file.language, &source)
        .map_err(|error| format!("{}: {error}", file.path.display()))?;
    let sloc_lines = syntax.sloc_lines.clone();
    let parsed_directives = if file.language == Language::Python {
        parse_source_directives(&file.path, &source, &syntax.comments, valid_rule_ids)
            .map_err(|error| format!("directive error: {error}"))?
    } else {
        ParsedDirectives {
            ignores: Vec::new(),
            boundaries: Vec::new(),
        }
    };
    let functions: Vec<Function> = syntax
        .functions
        .iter()
        .map(|span| build_function(&file.path, file.language, span, &lines, &sloc_lines))
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
    let ast_grep_findings = if disable_sg || file.language != Language::Python {
        Vec::new()
    } else {
        run_python_rules(&file.path, &source, include_all)?
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
        node_count: syntax.node_count,
        source_lines: SourceLines {
            file: file.path.clone(),
            lines: lines.iter().map(|line| (*line).to_string()).collect(),
        },
    })
}

fn valid_rule_ids() -> Result<BTreeSet<String>, String> {
    let ast_ids: BTreeSet<String> = ast_grep_rule_ids()?.into_iter().collect();
    let structural_ids: BTreeSet<String> = structural_rule_ids()
        .into_iter()
        .map(ToString::to_string)
        .collect();
    if let Some(duplicate) = ast_ids.intersection(&structural_ids).next() {
        return Err(format!("duplicate rule id: {duplicate}"));
    }
    Ok(ast_ids.union(&structural_ids).cloned().collect())
}

fn apply_count_thresholds(findings: Vec<AstGrepFinding>) -> Result<Vec<AstGrepFinding>, String> {
    let thresholds = ast_grep_thresholds()?;
    if thresholds.is_empty() {
        return Ok(findings);
    }

    let mut counts: BTreeMap<(String, PathBuf), usize> = BTreeMap::new();
    for finding in &findings {
        if thresholds.contains_key(&finding.rule_id) {
            *counts
                .entry((finding.rule_id.clone(), finding.file.clone()))
                .or_insert(0) += 1;
        }
    }

    Ok(findings
        .into_iter()
        .filter(|finding| {
            let Some(threshold) = thresholds.get(&finding.rule_id) else {
                return true;
            };
            counts
                .get(&(finding.rule_id.clone(), finding.file.clone()))
                .is_some_and(|count| count >= threshold)
        })
        .collect())
}

fn read_source(path: &Path) -> Result<String, std::io::Error> {
    match fs::read_to_string(path) {
        Ok(source) => Ok(source),
        Err(error) if error.kind() == std::io::ErrorKind::InvalidData => {
            fs::read(path).map(|bytes| String::from_utf8_lossy(&bytes).into_owned())
        }
        Err(error) => Err(error),
    }
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

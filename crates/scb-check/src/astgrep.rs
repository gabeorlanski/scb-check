use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use ast_grep_config::{GlobalRules, Severity, from_yaml_string};
use ast_grep_language::{LanguageExt, SupportLang};

use crate::model::AstGrepFinding;

const BUNDLED_RULES: &[(&str, &str)] = &[
    (
        "boolean_and_comparison.yaml",
        include_str!("../resources/slop_rules/boolean_and_comparison.yaml"),
    ),
    (
        "conditionals.yaml",
        include_str!("../resources/slop_rules/conditionals.yaml"),
    ),
    (
        "defensive.yaml",
        include_str!("../resources/slop_rules/defensive.yaml"),
    ),
    (
        "dict_patterns.yaml",
        include_str!("../resources/slop_rules/dict_patterns.yaml"),
    ),
    (
        "loops_and_comprehensions.yaml",
        include_str!("../resources/slop_rules/loops_and_comprehensions.yaml"),
    ),
    (
        "misc.yaml",
        include_str!("../resources/slop_rules/misc.yaml"),
    ),
    (
        "type_annotations.yaml",
        include_str!("../resources/slop_rules/type_annotations.yaml"),
    ),
    (
        "type_conversions.yaml",
        include_str!("../resources/slop_rules/type_conversions.yaml"),
    ),
];

const EXTRA_RULES_ENV: &str = "SCB_CHECK_EXTRA_SLOP_RULES";

#[derive(Debug, Clone, PartialEq, Eq)]
struct RuleText {
    name: String,
    yaml: String,
}

pub(crate) fn run_python_rules(
    path: &Path,
    source: &str,
    include_all: bool,
) -> Result<Vec<AstGrepFinding>, String> {
    let rules = load_rules()?;
    let grep = SupportLang::Python.ast_grep(source);
    let root = grep.root();
    let mut findings = Vec::new();
    for rule in rules {
        if skip_rule(&rule.severity, include_all) {
            continue;
        }
        for matched in root.find_all(&rule.matcher) {
            findings.push(AstGrepFinding {
                rule_id: rule.id.clone(),
                severity: severity_text(&rule.severity).to_string(),
                message: rule.get_message(&matched),
                file: path.to_path_buf(),
                start_line: matched.start_pos().line() + 1,
                end_line: matched.end_pos().line() + 1,
                start_col: matched.start_pos().column(&matched),
                end_col: matched.end_pos().column(&matched),
                matched_text: matched.text().to_string(),
            });
        }
    }
    findings.sort_by(|left, right| {
        (
            left.file.as_os_str(),
            left.start_line,
            left.end_line,
            left.start_col,
            left.end_col,
            left.rule_id.as_str(),
            left.severity.as_str(),
            left.message.as_str(),
            left.matched_text.as_str(),
        )
            .cmp(&(
                right.file.as_os_str(),
                right.start_line,
                right.end_line,
                right.start_col,
                right.end_col,
                right.rule_id.as_str(),
                right.severity.as_str(),
                right.message.as_str(),
                right.matched_text.as_str(),
            ))
    });
    findings.dedup_by(same_finding);
    Ok(findings)
}

fn same_finding(left: &mut AstGrepFinding, right: &mut AstGrepFinding) -> bool {
    left.file == right.file
        && left.start_line == right.start_line
        && left.end_line == right.end_line
        && left.start_col == right.start_col
        && left.end_col == right.end_col
        && left.rule_id == right.rule_id
        && left.severity == right.severity
        && left.message == right.message
        && left.matched_text == right.matched_text
}

pub(crate) fn ast_grep_rule_ids() -> Result<Vec<String>, String> {
    let texts = bundled_and_extra_rule_texts()?;
    validate_rule_texts(&texts)?;
    let mut ids = Vec::new();
    let mut seen = BTreeSet::new();
    for text in &texts {
        for document in split_yaml_documents(&text.yaml) {
            let Some(rule_id) = document_rule_id(document) else {
                continue;
            };
            if !seen.insert(rule_id.to_string()) {
                return Err(format!("duplicate rule id: {rule_id}"));
            }
            ids.push(rule_id.to_string());
        }
    }
    Ok(ids)
}

pub(crate) fn ast_grep_thresholds() -> Result<BTreeMap<String, usize>, String> {
    let texts = bundled_and_extra_rule_texts()?;
    validate_rule_texts(&texts)?;
    let mut thresholds = BTreeMap::new();
    for text in &texts {
        for document in split_yaml_documents(&text.yaml) {
            let Some(rule_id) = document_rule_id(document) else {
                continue;
            };
            if let Some(threshold) = document_min_file_count(document) {
                thresholds.insert(rule_id.to_string(), threshold);
            }
        }
    }
    Ok(thresholds)
}

pub(crate) fn ast_grep_rule_document(rule_id: &str) -> Result<Option<String>, String> {
    let texts = bundled_and_extra_rule_texts()?;
    validate_rule_texts(&texts)?;
    for text in &texts {
        for document in split_yaml_documents(&text.yaml) {
            if document_rule_id(document).is_some_and(|id| id == rule_id) {
                return Ok(Some(document.trim().to_string()));
            }
        }
    }
    Ok(None)
}

fn document_min_file_count(document: &str) -> Option<usize> {
    for line in document.lines() {
        let trimmed = line.trim();
        if let Some(raw) = trimmed.strip_prefix("min_file_count:") {
            let count = raw.trim().parse::<usize>().ok()?;
            if count > 1 {
                return Some(count);
            }
        }
    }
    None
}

fn load_rules() -> Result<Vec<ast_grep_config::RuleConfig<SupportLang>>, String> {
    let globals = GlobalRules::default();
    let mut rules = Vec::new();
    for text in bundled_and_extra_rule_texts()? {
        extend_rules(&mut rules, &text, &globals)?;
    }
    Ok(rules)
}

fn bundled_and_extra_rule_texts() -> Result<Vec<RuleText>, String> {
    let mut texts = BUNDLED_RULES
        .iter()
        .map(|(name, yaml)| RuleText {
            name: (*name).to_string(),
            yaml: (*yaml).to_string(),
        })
        .collect::<Vec<_>>();
    if let Some(paths) = std::env::var_os(EXTRA_RULES_ENV) {
        for path in std::env::split_paths(&paths) {
            texts.push(extra_rule_text(&path)?);
        }
    }
    Ok(texts)
}

fn extra_rule_text(path: &Path) -> Result<RuleText, String> {
    let yaml = fs::read_to_string(path).map_err(|error| {
        format!(
            "failed to read ast-grep rule file {}: {error}",
            path.display()
        )
    })?;
    Ok(RuleText {
        name: path.display().to_string(),
        yaml,
    })
}

fn split_yaml_documents(yaml: &str) -> impl Iterator<Item = &str> {
    yaml.split("\n---")
        .map(|document| document.trim_start_matches('-').trim())
        .filter(|document| !document.is_empty())
}

fn document_rule_id(document: &str) -> Option<&str> {
    document.lines().find_map(|line| {
        let trimmed = line.trim();
        let raw = trimmed.strip_prefix("id:")?.trim();
        Some(raw.trim_matches('"').trim_matches('\''))
    })
}

fn extend_rules(
    rules: &mut Vec<ast_grep_config::RuleConfig<SupportLang>>,
    text: &RuleText,
    globals: &GlobalRules,
) -> Result<(), String> {
    let mut parsed = from_yaml_string::<SupportLang>(&text.yaml, globals)
        .map_err(|error| format!("failed to parse ast-grep rule file {}: {error}", text.name))?;
    rules.append(&mut parsed);
    Ok(())
}

fn validate_rule_texts(texts: &[RuleText]) -> Result<(), String> {
    let globals = GlobalRules::default();
    for text in texts {
        let _ = from_yaml_string::<SupportLang>(&text.yaml, &globals).map_err(|error| {
            format!("failed to parse ast-grep rule file {}: {error}", text.name)
        })?;
    }
    Ok(())
}

const fn skip_rule(severity: &Severity, include_all: bool) -> bool {
    matches!(severity, Severity::Off)
        || (!include_all && matches!(severity, Severity::Hint | Severity::Info))
}

const fn severity_text(severity: &Severity) -> &'static str {
    match severity {
        Severity::Hint | Severity::Info => "info",
        Severity::Warning | Severity::Off => "warning",
        Severity::Error => "critical",
    }
}

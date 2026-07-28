use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use ast_grep_config::{GlobalRules, Severity, from_yaml_string};
use ast_grep_language::{LanguageExt, SupportLang};

use crate::model::AstGrepFinding;

const BUNDLED_RULES: &[(&str, &str)] = &[
    (
        "boolean_and_comparison.yaml",
        include_str!("languages/python/ast_grep_rules/boolean_and_comparison.yaml"),
    ),
    (
        "conditionals.yaml",
        include_str!("languages/python/ast_grep_rules/conditionals.yaml"),
    ),
    (
        "defensive.yaml",
        include_str!("languages/python/ast_grep_rules/defensive.yaml"),
    ),
    (
        "dict_patterns.yaml",
        include_str!("languages/python/ast_grep_rules/dict_patterns.yaml"),
    ),
    (
        "loops_and_comprehensions.yaml",
        include_str!("languages/python/ast_grep_rules/loops_and_comprehensions.yaml"),
    ),
    (
        "misc.yaml",
        include_str!("languages/python/ast_grep_rules/misc.yaml"),
    ),
    (
        "type_annotations.yaml",
        include_str!("languages/python/ast_grep_rules/type_annotations.yaml"),
    ),
    (
        "type_conversions.yaml",
        include_str!("languages/python/ast_grep_rules/type_conversions.yaml"),
    ),
];

const EXTRA_RULES_ENV: &str = "SCB_CHECK_EXTRA_SLOP_RULES";

#[derive(Debug, Clone, PartialEq, Eq)]
struct RuleText {
    name: String,
    yaml: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RuleDocument {
    id: String,
    yaml: String,
    min_file_count: Option<usize>,
}

pub struct AstGrepCatalog {
    rules: Vec<ast_grep_config::RuleConfig<SupportLang>>,
    documents: Vec<RuleDocument>,
}

impl AstGrepCatalog {
    /// Load the bundled rules together with rules configured through the environment.
    ///
    /// The catalog owns parsed rules and their source documents so analysis can borrow one stable
    /// collection for every file instead of reparsing rule YAML in the per-file loop.
    pub fn load() -> Result<Self, String> {
        Self::from_texts(bundled_and_extra_rule_texts()?)
    }

    fn from_texts(texts: Vec<RuleText>) -> Result<Self, String> {
        let globals = GlobalRules::default();
        let mut rules = Vec::new();
        let mut documents = Vec::new();
        let mut seen = BTreeSet::new();
        for text in texts {
            extend_rules(&mut rules, &text, &globals)?;
            for document in rule_documents(&text) {
                if !seen.insert(document.id.clone()) {
                    return Err(format!("duplicate rule id: {}", document.id));
                }
                documents.push(document);
            }
        }
        Ok(Self { rules, documents })
    }

    /// Return loaded ast-grep rule identifiers in catalog order.
    pub fn rule_ids(&self) -> Vec<String> {
        self.documents
            .iter()
            .map(|document| document.id.clone())
            .collect()
    }

    /// Return configured per-rule file-count thresholds.
    pub fn thresholds(&self) -> BTreeMap<String, usize> {
        self.documents
            .iter()
            .filter_map(|document| {
                document
                    .min_file_count
                    .map(|threshold| (document.id.clone(), threshold))
            })
            .collect()
    }

    /// Return the YAML document for one loaded rule, if present.
    pub fn rule_document(&self, rule_id: &str) -> Option<String> {
        self.documents
            .iter()
            .find(|document| document.id == rule_id)
            .map(|document| document.yaml.clone())
    }

    /// Run applicable ast-grep rules against one source file and return sorted, deduplicated findings.
    pub fn run_rules(
        &self,
        language: SupportLang,
        path: &Path,
        source: &str,
        include_all: bool,
    ) -> Vec<AstGrepFinding> {
        let grep = language.ast_grep(source);
        let root = grep.root();
        let mut findings = Vec::new();
        for rule in &self.rules {
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
        findings
    }
}

/// Load and return the YAML document for an ast-grep rule identifier.
pub fn ast_grep_rule_document(rule_id: &str) -> Result<Option<String>, String> {
    Ok(AstGrepCatalog::load()?.rule_document(rule_id))
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

fn rule_documents(text: &RuleText) -> Vec<RuleDocument> {
    let mut documents = Vec::new();
    for document in split_yaml_documents(&text.yaml) {
        let Some(rule_id) = document_rule_id(document) else {
            continue;
        };
        documents.push(RuleDocument {
            id: rule_id.to_string(),
            yaml: document.trim().to_string(),
            min_file_count: document_min_file_count(document),
        });
    }
    documents
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

#[cfg(test)]
mod tests {
    use super::{AstGrepCatalog, RuleText, ast_grep_rule_document, extra_rule_text};
    use crate::test_support::{test_dir, write};
    use ast_grep_language::SupportLang;

    #[test]
    fn bundled_python_rules_run_in_process_and_can_be_skipped_by_callers() {
        let catalog = AstGrepCatalog::load().expect("catalog should load");
        let findings = catalog.run_rules(
            SupportLang::Python,
            std::path::Path::new("sample.py"),
            r"
def item_names(items):
    for index in range(len(items)):
        print(items[index])
",
            false,
        );

        assert!(
            findings
                .iter()
                .any(|finding| finding.rule_id == "for-range-len")
        );
    }

    #[test]
    fn duplicate_ast_grep_rule_ids_are_usage_errors() {
        let texts = vec![RuleText {
            name: "duplicate.yaml".to_string(),
            yaml: r"
---
id: env-duplicate-rule
language: python
severity: warning
message: first duplicate
rule:
  pattern: pass
---
id: env-duplicate-rule
language: python
severity: warning
message: second duplicate
rule:
  pattern: pass
"
            .to_string(),
        }];

        let Err(error) = AstGrepCatalog::from_texts(texts) else {
            panic!("duplicate ids should fail");
        };

        assert_eq!(error, "duplicate rule id: env-duplicate-rule");
    }

    #[test]
    fn invalid_extra_ast_grep_rule_sources_are_usage_errors() {
        let root = test_dir();
        let missing = root.join("missing-rules.yaml");
        let missing_error = extra_rule_text(&missing).expect_err("missing file should fail");
        assert!(missing_error.contains("failed to read ast-grep rule file"));
        assert!(missing_error.contains("missing-rules.yaml"));

        let invalid = root.join("invalid-rules.yaml");
        write(&invalid, ":\n");
        let text = extra_rule_text(&invalid).expect("invalid yaml should still be readable");
        let Err(invalid_error) = AstGrepCatalog::from_texts(vec![text]) else {
            panic!("invalid yaml should fail");
        };
        assert!(invalid_error.contains("failed to parse ast-grep rule file"));
        assert!(invalid_error.contains("invalid-rules.yaml"));
    }

    #[test]
    fn ast_grep_rule_document_prints_bundled_yaml() {
        let document = ast_grep_rule_document("chained-dict-get")
            .expect("rule lookup should succeed")
            .expect("rule should exist");

        assert!(document.contains("id: chained-dict-get"));
        assert!(document.contains("language: python"));
    }
}

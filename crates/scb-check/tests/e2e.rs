use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use assert_cmd::Command as AssertCommand;
use assert_fs::prelude::*;
use predicates::str::contains;
use serde_json::json;

#[test]
fn reports_python_and_rust_json_contract() {
    let root = test_dir("python-rust-json");
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

    let output = run_check(&root);

    assert!(!output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");
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
        assert!(stdout.contains(&format!("\"{key}\"")), "missing key {key}");
    }
    assert!(stdout.contains("\"files_scanned\":2"));
    assert!(stdout.contains("\"total_functions\":4"));
    assert!(stdout.contains("\"python\""));
    assert!(stdout.contains("\"rust\""));
    assert!(!stdout.contains("-0"));
}

#[test]
fn cutover_fixture_json_reports_match_expected_values() {
    for case in cutover_json_cases() {
        let fixture = workspace_root()
            .join("tests/fixtures/rust_cutover_parity")
            .join(case.name);
        let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
            .args(["check", "--report"])
            .args(case.disable_sg.then_some("--disable-sg"))
            .arg("--config")
            .arg(fixture.join("scb-check.toml"))
            .arg(&fixture)
            .output()
            .expect("scb-check should run");
        let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");
        let actual: serde_json::Value =
            serde_json::from_str(&stdout).expect("stdout should be json");

        assert_eq!(output.status.code(), case.exit_code, "{}", case.name);
        assert_eq!(actual, case.expected, "{}", case.name);
    }
}

struct CutoverJsonCase {
    name: &'static str,
    disable_sg: bool,
    exit_code: Option<i32>,
    expected: serde_json::Value,
}

#[allow(
    clippy::approx_constant,
    clippy::too_many_lines,
    clippy::unreadable_literal,
    reason = "exact JSON report contract values should mirror serialized output"
)]
fn cutover_json_cases() -> Vec<CutoverJsonCase> {
    vec![
        CutoverJsonCase {
            name: "scoreless_mixed",
            disable_sg: true,
            exit_code: Some(0),
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
                    "rust": {"node_count": 13, "tree_count": 1},
                },
                "syntax_node_count": 19,
                "syntax_tree_count": 2,
                "total_cog_mass": 0.0,
                "total_functions": 1,
                "total_loc": 3,
                "total_mass": 1.4142135623730951,
                "verbosity": 0.0,
                "verbosity_flagged_loc": 0,
            }),
        },
        CutoverJsonCase {
            name: "python_wrapper",
            disable_sg: true,
            exit_code: Some(1),
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
                "syntax_by_language": {
                    "python": {"node_count": 13, "tree_count": 1},
                },
                "syntax_node_count": 13,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 1,
                "total_loc": 2,
                "total_mass": 1.4142135623730951,
                "verbosity": 1.0,
                "verbosity_flagged_loc": 2,
            }),
        },
        CutoverJsonCase {
            name: "python_clone",
            disable_sg: true,
            exit_code: Some(1),
            expected: json!({
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
                "syntax_by_language": {
                    "python": {"node_count": 57, "tree_count": 1},
                },
                "syntax_node_count": 57,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 2,
                "total_loc": 8,
                "total_mass": 4.0,
                "verbosity": 1.0,
                "verbosity_flagged_loc": 8,
            }),
        },
        CutoverJsonCase {
            name: "python_low_use",
            disable_sg: true,
            exit_code: Some(1),
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
                "structural_rule_findings": 2,
                "structural_rule_loc": 5,
                "syntax_by_language": {
                    "python": {"node_count": 42, "tree_count": 1},
                },
                "syntax_node_count": 42,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 2,
                "total_loc": 5,
                "total_mass": 3.146264369941973,
                "verbosity": 1.0,
                "verbosity_flagged_loc": 5,
            }),
        },
        CutoverJsonCase {
            name: "rust_clone",
            disable_sg: true,
            exit_code: Some(1),
            expected: json!({
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
                "syntax_by_language": {
                    "rust": {"node_count": 69, "tree_count": 1},
                },
                "syntax_node_count": 69,
                "syntax_tree_count": 1,
                "total_cog_mass": 0.0,
                "total_functions": 2,
                "total_loc": 8,
                "total_mass": 4.0,
                "verbosity": 1.0,
                "verbosity_flagged_loc": 8,
            }),
        },
        CutoverJsonCase {
            name: "python_astgrep",
            disable_sg: false,
            exit_code: Some(1),
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
                "syntax_by_language": {
                    "python": {"node_count": 38, "tree_count": 1},
                },
                "syntax_node_count": 38,
                "syntax_tree_count": 1,
                "total_cog_mass": 1.7320508075688772,
                "total_functions": 1,
                "total_loc": 3,
                "total_mass": 3.4641016151377544,
                "verbosity": 0.6666666666666666,
                "verbosity_flagged_loc": 2,
            }),
        },
    ]
}

#[test]
fn output_format_and_report_keep_last_option_wins_behavior() {
    let root = test_dir("output-format-order");
    write(&root.join("sample.py"), "value = 1\n");

    let human_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args([
            "check",
            "--report",
            "--output-format",
            "human",
            "--disable-sg",
        ])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let human_stdout = String::from_utf8(human_output.stdout).expect("stdout should be utf-8");

    assert!(human_output.status.success());
    assert!(human_stdout.is_empty());

    let json_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args([
            "check",
            "--output-format",
            "human",
            "--report",
            "--disable-sg",
        ])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let json_stdout = String::from_utf8(json_output.stdout).expect("stdout should be utf-8");

    assert!(json_output.status.success());
    assert!(json_stdout.contains("\"files_scanned\":1"));
}

#[test]
fn verbosity_flags_write_diagnostics_to_stderr_only() {
    let root = test_dir("verbosity-flags");
    write(&root.join("sample.py"), "value = 1\n");

    let info_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg", "-v"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let info_stdout = String::from_utf8(info_output.stdout).expect("stdout should be utf-8");
    let info_stderr = String::from_utf8(info_output.stderr).expect("stderr should be utf-8");

    assert!(info_output.status.success());
    assert!(serde_json::from_str::<serde_json::Value>(&info_stdout).is_ok());
    assert!(info_stderr.contains("info files_discovered count=1"));
    assert!(info_stderr.contains("info analysis_complete files_scanned=1"));
    assert!(!info_stderr.contains("debug source_file"));

    let debug_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg", "-vv"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let debug_stdout = String::from_utf8(debug_output.stdout).expect("stdout should be utf-8");
    let debug_stderr = String::from_utf8(debug_output.stderr).expect("stderr should be utf-8");

    assert!(debug_output.status.success());
    assert!(serde_json::from_str::<serde_json::Value>(&debug_stdout).is_ok());
    assert!(debug_stderr.contains("debug config_loaded"));
    assert!(debug_stderr.contains("debug source_file language=python"));
}

#[test]
fn ignores_non_cutover_languages_in_directory_scan() {
    let root = test_dir("ignored-languages");
    write(&root.join("sample.py"), "value = 1\n");
    write(&root.join("sample.rs"), "fn value() -> i32 {\n    1\n}\n");
    write(&root.join("sample.js"), "function value() { return 1 }\n");
    write(&root.join("sample.ts"), "const value: number = 1\n");
    write(&root.join("sample.go"), "package main\n");

    let output = run_check(&root);
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(stdout.contains("\"files_scanned\":2"));
    assert!(stdout.contains("\"python\""));
    assert!(stdout.contains("\"rust\""));
    assert!(!stdout.contains("javascript"));
    assert!(!stdout.contains("typescript"));
    assert!(!stdout.contains("\"go\""));
}

#[test]
fn explicit_unsupported_file_exits_two() {
    let root = assert_fs::TempDir::new().expect("test dir should be created");
    let source = root.child("sample.go");
    source
        .write_str("package main\n")
        .expect("fixture should be writable");

    AssertCommand::cargo_bin("scb-check")
        .expect("scb-check binary should exist")
        .args(["check", "--report"])
        .arg(source.path())
        .assert()
        .code(2)
        .stderr(contains("not a supported source file"));
}

#[test]
fn applies_scb_config_excludes() {
    let root = test_dir("config-excludes");
    write(
        &root.join("scb-check.toml"),
        "exclude = [\"generated/**\"]\n",
    );
    fs::create_dir(root.join("generated")).expect("generated dir should be created");
    write(&root.join("keep.py"), "value = 1\n");
    write(&root.join("generated").join("skip.py"), "value = 2\n");
    write(&root.join("keep.rs"), "fn value() -> i32 {\n    1\n}\n");

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg", "--config"])
        .arg(root.join("scb-check.toml"))
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(stdout.contains("\"files_scanned\":2"));
}

#[test]
fn imports_pyproject_tool_excludes() {
    let root = test_dir("pyproject-excludes");
    write(
        &root.join("pyproject.toml"),
        r#"
[tool.ruff]
exclude = ["vendor/"]

[tool.ty.src]
exclude = ["fixtures/"]
"#,
    );
    fs::create_dir(root.join("vendor")).expect("vendor dir should be created");
    fs::create_dir(root.join("fixtures")).expect("fixtures dir should be created");
    write(&root.join("keep.py"), "value = 1\n");
    write(&root.join("vendor").join("skip.py"), "value = 2\n");
    write(
        &root.join("fixtures").join("skip.rs"),
        "fn value() -> i32 { 1 }\n",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg", "--config"])
        .arg(root.join("pyproject.toml"))
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(output.status.success());
    assert!(stdout.contains("\"files_scanned\":1"));
}

#[test]
fn include_all_includes_gitignored_but_not_default_excluded_dirs() {
    let root = test_dir("gitignore-include-all");
    write(&root.join(".gitignore"), "ignored.py\n");
    fs::create_dir(root.join("node_modules")).expect("node_modules dir should be created");
    write(&root.join("keep.py"), "value = 1\n");
    write(&root.join("ignored.py"), "value = 2\n");
    write(&root.join("node_modules").join("skip.py"), "value = 3\n");

    let default_output = run_check(&root);
    let default_stdout = String::from_utf8(default_output.stdout).expect("stdout should be utf-8");
    assert!(default_stdout.contains("\"files_scanned\":1"));

    let include_all_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg", "--include-all"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let include_all_stdout =
        String::from_utf8(include_all_output.stdout).expect("stdout should be utf-8");
    assert!(include_all_stdout.contains("\"files_scanned\":2"));
}

#[test]
fn shared_structural_wrapper_rule_runs_on_python_and_rust_ir() {
    let root = test_dir("shared-wrapper-rule");
    write(
        &root.join("sample.py"),
        r"
def identity(value):
    return value

def forward(value):
    return identity(value)

def branch(value):
    if value:
        return value
    return None
",
    );
    write(
        &root.join("sample.rs"),
        r"
fn identity(value: i32) -> i32 {
    value
}

fn forward(value: i32) -> i32 {
    identity(value)
}

fn branch(value: i32) -> i32 {
    if value > 0 {
        return value;
    }
    0
}
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert_eq!(stdout.matches("trivial-wrapper[warning]").count(), 4);
    assert!(stdout.contains("sample.py:1"));
    assert!(stdout.contains("sample.py:4"));
    assert!(stdout.contains("sample.rs:1"));
    assert!(stdout.contains("sample.rs:5"));
    assert!(!stdout.contains("branch` adds no behavior"));
}

#[test]
fn low_use_short_function_is_opt_in_and_runs_on_python_and_rust_ir() {
    let root = test_dir("short-helper");
    write(
        &root.join("sample.py"),
        r"
def clean(value):
    normalized = value.strip()
    return normalized

def route(value):
    return clean(value)
",
    );
    write(
        &root.join("sample.rs"),
        r"
fn clean(value: &str) -> String {
    let normalized = value.trim();
    normalized.to_string()
}

fn route(value: &str) -> String {
    clean(value)
}
",
    );

    let default_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let default_stdout = String::from_utf8(default_output.stdout).expect("stdout should be utf-8");
    assert!(!default_stdout.contains("low-use-short-function"));

    let config = root.join("scb-check.toml");
    write(&config, "[low-use-short-function]\nenabled = true\n");
    let enabled_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg", "--config"])
        .arg(&config)
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let enabled_stdout = String::from_utf8(enabled_output.stdout).expect("stdout should be utf-8");

    assert_eq!(enabled_output.status.code(), Some(1));
    assert_eq!(
        enabled_stdout
            .matches("low-use-short-function[info]")
            .count(),
        2
    );
    assert!(enabled_stdout.contains("sample.py:1"));
    assert!(enabled_stdout.contains("sample.rs:1"));
}

#[test]
fn low_use_short_function_honors_python_ignore_directives() {
    let root = test_dir("low-use-ignore");
    let config = root.join("scb-check.toml");
    write(&config, "[low-use-short-function]\nenabled = true\n");
    write(
        &root.join("sample.py"),
        r"
# scbc ignore[low-use-short-function]
def clean(value):
    normalized = value.strip()
    return normalized

def route(value):
    return clean(value)
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg", "--config"])
        .arg(&config)
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert!(!stdout.contains("low-use-short-function"));
    assert!(stdout.contains("trivial-wrapper[warning]"));
}

#[test]
fn pyproject_low_use_short_function_settings_are_supported() {
    let root = test_dir("pyproject-short-helper");
    let config = root.join("pyproject.toml");
    write(
        &config,
        "[tool.scb-check.low-use-short-function]\nenabled = true\n",
    );
    write(
        &root.join("sample.py"),
        r"
def clean(value):
    normalized = value.strip()
    return normalized

def route(value):
    return clean(value)
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg", "--config"])
        .arg(&config)
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout.contains("low-use-short-function[info]"));
}

#[test]
fn parser_finds_python_methods_and_rust_impl_methods() {
    let root = test_dir("parser-methods");
    write(
        &root.join("sample.py"),
        r"
class Thing:
    def same(self, value):
        return value
",
    );
    write(
        &root.join("sample.rs"),
        r"
struct Thing;

impl Thing {
    fn same(&self, value: i32) -> i32 {
        value
    }
}
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert_eq!(stdout.matches("trivial-wrapper[warning]").count(), 2);
    assert!(stdout.contains("sample.py:2"));
    assert!(stdout.contains("sample.rs:4"));
}

#[test]
fn complexity_metrics_ignore_branch_text_and_rust_match_arms() {
    let root = test_dir("complexity-branch-text");
    write(
        &root.join("sample.py"),
        r#"
def message():
    text = "if elif for while match and or"
    return text.upper()
"#,
    );
    write(
        &root.join("sample.rs"),
        r#"
fn classify(value: i32) -> &'static str {
    match value {
        0 => "if for while loop match =>",
        1 => "one",
        _ => "many",
    }
}
"#,
    );

    let output = run_check(&root);
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(output.status.success());
    assert!(stdout.contains("\"high_cc_functions\":0"));
    assert!(stdout.contains("\"high_cog_functions\":0"));
}

#[test]
fn ast_grep_python_rules_run_in_process_and_disable_sg_skips_them() {
    let root = test_dir("ast-grep-python");
    write(
        &root.join("sample.py"),
        r"
def item_names(items):
    for index in range(len(items)):
        print(items[index])
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout.contains("warning[for-range-len]"));

    let disabled_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let disabled_stdout =
        String::from_utf8(disabled_output.stdout).expect("stdout should be utf-8");
    assert!(disabled_output.status.success());
    assert!(!disabled_stdout.contains("for-range-len"));

    let report_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let report_stdout = String::from_utf8(report_output.stdout).expect("stdout should be utf-8");
    assert!(report_stdout.contains("\"ast_grep_flagged_loc\":"));
    assert!(!report_stdout.contains("\"ast_grep_flagged_loc\":0"));
}

#[test]
fn human_output_orders_mixed_findings_and_renders_context_lines() {
    let root = test_dir("human-context-order");
    let config = root.join("scb-check.toml");
    write(&config, "context = 1\n");
    write(
        &root.join("sample.py"),
        r"
def identity(value):
    return value

def noisy(items):
    for index in range(len(items)):
        print(items[index])
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--config"])
        .arg(&config)
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    let structural_index = stdout
        .find("trivial-wrapper[warning]")
        .expect("structural finding should render");
    let ast_index = stdout
        .find("warning[for-range-len]")
        .expect("ast-grep finding should render");
    assert!(structural_index < ast_index);
    assert!(stdout.contains("1 | def identity(value):"));
    assert!(stdout.contains("2 |     return value"));
    assert!(stdout.contains("4 | def noisy(items):"));
    assert!(stdout.contains("5 |     for index in range(len(items)):"));
    assert!(stdout.contains("6 |         print(items[index])"));
}

#[test]
fn duplicate_rule_ids_are_usage_errors() {
    let cases = [
        (
            "ast-grep-duplicate-id",
            r"
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
",
            "duplicate rule id: env-duplicate-rule",
        ),
        (
            "ast-grep-structural-id",
            r"
---
id: trivial-wrapper
language: python
severity: warning
message: structural collision
rule:
  pattern: pass
",
            "duplicate rule id: trivial-wrapper",
        ),
    ];

    for (name, yaml, expected) in cases {
        let root = test_dir(name);
        let rules = root.join("rules.yaml");
        write(&rules, yaml);
        write(
            &root.join("sample.py"),
            r"
def placeholder():
    pass
",
        );

        let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
            .arg("check")
            .arg(&root)
            .env("SCB_CHECK_EXTRA_SLOP_RULES", &rules)
            .output()
            .expect("scb-check should run");
        let stderr = String::from_utf8(output.stderr).expect("stderr should be utf-8");

        assert_eq!(output.status.code(), Some(2));
        assert!(stderr.contains(expected));
    }
}

#[test]
fn invalid_extra_ast_grep_rule_sources_are_usage_errors() {
    let root = test_dir("ast-grep-extra-rule-errors");
    write(
        &root.join("sample.py"),
        r"
def placeholder():
    pass
",
    );
    let missing = root.join("missing-rules.yaml");
    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .arg("check")
        .arg(&root)
        .env("SCB_CHECK_EXTRA_SLOP_RULES", &missing)
        .output()
        .expect("scb-check should run");
    let stderr = String::from_utf8(output.stderr).expect("stderr should be utf-8");

    assert_eq!(output.status.code(), Some(2));
    assert!(stderr.contains("failed to read ast-grep rule file"));
    assert!(stderr.contains("missing-rules.yaml"));

    let invalid = root.join("invalid-rules.yaml");
    write(&invalid, ":\n");
    let invalid_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .arg("check")
        .arg(&root)
        .env("SCB_CHECK_EXTRA_SLOP_RULES", &invalid)
        .output()
        .expect("scb-check should run");
    let invalid_stderr = String::from_utf8(invalid_output.stderr).expect("stderr should be utf-8");

    assert_eq!(invalid_output.status.code(), Some(2));
    assert!(invalid_stderr.contains("failed to parse ast-grep rule file"));
    assert!(invalid_stderr.contains("invalid-rules.yaml"));
}

#[test]
fn ast_grep_min_file_count_thresholds_filter_sparse_files() {
    let root = test_dir("ast-grep-threshold");
    let rules = root.join("threshold-rules.yaml");
    write(
        &rules,
        r"
---
id: env-threshold-pass
language: python
severity: warning
message: threshold pass
metadata:
  min_file_count: 2
rule:
  pattern: pass
",
    );
    write(
        &root.join("sparse.py"),
        r"
def one():
    pass
",
    );
    write(
        &root.join("dense.py"),
        r"
def one():
    pass

def two():
    pass
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .arg("check")
        .arg(&root)
        .env("SCB_CHECK_EXTRA_SLOP_RULES", &rules)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert_eq!(stdout.matches("warning[env-threshold-pass]").count(), 2);
    assert!(stdout.contains("dense.py"));
    assert!(!stdout.contains("sparse.py"));

    let include_all_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--include-all"])
        .arg(&root)
        .env("SCB_CHECK_EXTRA_SLOP_RULES", &rules)
        .output()
        .expect("scb-check should run");
    let include_all_stdout =
        String::from_utf8(include_all_output.stdout).expect("stdout should be utf-8");

    assert_eq!(include_all_output.status.code(), Some(1));
    assert_eq!(
        include_all_stdout
            .matches("warning[env-threshold-pass]")
            .count(),
        3
    );
    assert!(include_all_stdout.contains("sparse.py"));
}

#[test]
fn duplicate_python_and_rust_function_bodies_contribute_clone_loc() {
    let root = test_dir("clone-loc");
    write(
        &root.join("sample.py"),
        r"
def first(value):
    current = value + 1
    doubled = current * 2
    return doubled

def second(item):
    total = item + 2
    twice = total * 2
    return twice
",
    );
    write(
        &root.join("sample.rs"),
        r"
fn first(value: i32) -> i32 {
    let current = value + 1;
    let doubled = current * 2;
    doubled
}

fn second(item: i32) -> i32 {
    let total = item + 2;
    let twice = total * 2;
    twice
}
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert_eq!(output.status.code(), Some(1));
    assert_eq!(stdout.matches("duplicate-structure:").count(), 2);
    assert!(stdout.contains("┌─"));
    assert!(stdout.contains("│"));
    assert!(stdout.contains("sample.py:1"));
    assert!(stdout.contains("sample.rs:1"));

    let report_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let report_stdout = String::from_utf8(report_output.stdout).expect("stdout should be utf-8");
    assert!(report_stdout.contains("\"clone_loc\":"));
    assert!(!report_stdout.contains("\"clone_loc\":0"));
    assert!(!report_stdout.contains("\"verbosity_flagged_loc\":0"));

    let filtered_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg", "--min-duplicate-lines", "6"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let filtered_stdout =
        String::from_utf8(filtered_output.stdout).expect("stdout should be utf-8");
    assert_eq!(filtered_output.status.code(), Some(1));
    assert!(!filtered_stdout.contains("duplicate-structure:"));
}

#[test]
fn clone_fingerprints_preserve_operator_differences() {
    let root = test_dir("clone-operator-difference");
    write_operator_difference_fixture(&root);

    let output = run_check(&root);
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(output.status.success());
    assert!(stdout.contains("\"clone_loc\":0"));
    assert!(stdout.contains("\"verbosity_flagged_loc\":0"));
}

fn write_operator_difference_fixture(root: &Path) {
    let python = root.join("sample.py");
    let rust = root.join("sample.rs");
    write(
        &python,
        r"
def add(left, right):
    result = left + right
    doubled = result * 2
    return doubled

def subtract(left, right):
    result = left - right
    doubled = result * 2
    return doubled
",
    );
    write(
        &rust,
        r"
fn add(left: i32, right: i32) -> i32 {
    let result = left + right;
    let doubled = result * 2;
    doubled
}

fn subtract(left: i32, right: i32) -> i32 {
    let result = left - right;
    let doubled = result * 2;
    doubled
}
",
    );
}

#[test]
fn source_ignore_directives_suppress_ast_grep_and_structural_findings() {
    let root = test_dir("source-ignore");
    write(
        &root.join("sample.py"),
        r"
def noisy(items):
    for index in range(len(items)):  # scbc ignore[for-range-len] intentional index access
        print(items[index])

# scbc ignore[trivial-wrapper]
def identity(value):
    return value
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(output.status.success());
    assert!(!stdout.contains("for-range-len"));
    assert!(!stdout.contains("trivial-wrapper"));

    let include_all_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--include-all"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let include_all_stdout =
        String::from_utf8(include_all_output.stdout).expect("stdout should be utf-8");
    assert_eq!(include_all_output.status.code(), Some(1));
    assert!(include_all_stdout.contains("warning[for-range-len]"));
    assert!(include_all_stdout.contains("trivial-wrapper[warning]"));
}

#[test]
fn boundary_directive_suppresses_ast_grep_inside_function() {
    let root = test_dir("boundary-directive");
    write(
        &root.join("sample.py"),
        r"
def noisy(items):
    # scbc boundary: framework callback input shape
    for index in range(len(items)):
        print(items[index])
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");

    assert!(output.status.success());
    assert!(!stdout.contains("for-range-len"));

    let include_all_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--include-all"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let include_all_stdout =
        String::from_utf8(include_all_output.stdout).expect("stdout should be utf-8");
    assert_eq!(include_all_output.status.code(), Some(1));
    assert!(include_all_stdout.contains("warning[for-range-len]"));
}

#[test]
fn invalid_source_directive_is_usage_error() {
    let root = test_dir("invalid-directive");
    write(
        &root.join("sample.py"),
        r"
# scbc ignore[not-a-rule]
value = 1
",
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stderr = String::from_utf8(output.stderr).expect("stderr should be utf-8");

    assert_eq!(output.status.code(), Some(2));
    assert!(stderr.contains("unknown rule id: not-a-rule"));
}

#[test]
fn source_directive_text_inside_python_string_is_ignored() {
    let root = test_dir("directive-string");
    write(
        &root.join("sample.py"),
        r##"
def marker():
    return "# scbc ignore[not-a-rule]"

# scbc ignore[trivial-wrapper]
def identity(value):
    return value
"##,
    );

    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--disable-sg"])
        .arg(&root)
        .output()
        .expect("scb-check should run");
    let stdout = String::from_utf8(output.stdout).expect("stdout should be utf-8");
    let stderr = String::from_utf8(output.stderr).expect("stderr should be utf-8");

    assert!(output.status.success(), "{stderr}");
    assert!(!stdout.contains("trivial-wrapper"));
}

#[test]
fn rule_command_prints_ast_grep_yaml_and_structural_metadata() {
    let ast_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["rule", "chained-dict-get"])
        .output()
        .expect("scb-check should run");
    let ast_stdout = String::from_utf8(ast_output.stdout).expect("stdout should be utf-8");

    assert!(ast_output.status.success());
    assert!(ast_stdout.contains("id: chained-dict-get"));
    assert!(ast_stdout.contains("language: python"));

    let structural_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["rule", "trivial-wrapper"])
        .output()
        .expect("scb-check should run");
    let structural_stdout =
        String::from_utf8(structural_output.stdout).expect("stdout should be utf-8");

    assert!(structural_output.status.success());
    assert!(structural_stdout.contains("id: trivial-wrapper"));
    assert!(structural_stdout.contains("severity: warning"));
    assert!(structural_stdout.contains("target: symbol"));
    insta::assert_snapshot!(
        &structural_stdout,
        @r###"
id: trivial-wrapper
severity: warning
target: symbol
kind: structural
message: Function adds no behavior.
"###
    );

    let low_use_output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["rule", "low-use-short-function"])
        .output()
        .expect("scb-check should run");
    let low_use_stdout = String::from_utf8(low_use_output.stdout).expect("stdout should be utf-8");

    assert!(low_use_output.status.success());
    assert!(low_use_stdout.contains("id: low-use-short-function"));
    assert!(low_use_stdout.contains("severity: info"));
    assert!(low_use_stdout.contains("target: symbol"));
}

#[test]
fn rule_command_rejects_unknown_ids() {
    let output = Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["rule", "does-not-exist"])
        .output()
        .expect("scb-check should run");
    let stderr = String::from_utf8(output.stderr).expect("stderr should be utf-8");

    assert_eq!(output.status.code(), Some(2));
    assert!(stderr.contains("rule not found: does-not-exist"));
}

fn run_check(root: &Path) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg"])
        .arg(root)
        .output()
        .expect("scb-check should run")
}

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate should live under the workspace root")
        .to_path_buf()
}

fn write(path: &Path, content: &str) {
    fs::write(path, content.trim_start()).expect("fixture should be writable");
}

fn test_dir(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "scb-check-{name}-{}-{}",
        std::process::id(),
        nanos()
    ));
    fs::create_dir_all(&path).expect("test dir should be created");
    path
}

fn nanos() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system time should be after unix epoch")
        .as_nanos()
}

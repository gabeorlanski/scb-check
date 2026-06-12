mod support;

use std::process::Command;

use serde_json::json;

use support::{run_check, test_dir, workspace_root, write};

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

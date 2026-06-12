mod support;

use std::process::Command;

use support::{test_dir, write};

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

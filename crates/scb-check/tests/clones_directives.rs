mod support;

use std::path::Path;
use std::process::Command;

use support::{run_check, test_dir, write};

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

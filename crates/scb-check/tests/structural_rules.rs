mod support;

use std::process::Command;

use support::{test_dir, write};

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

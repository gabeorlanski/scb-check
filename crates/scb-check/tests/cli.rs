mod support;

use std::process::Command;

use assert_cmd::Command as AssertCommand;
use assert_fs::prelude::*;
use predicates::str::contains;

use support::{test_dir, write};

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

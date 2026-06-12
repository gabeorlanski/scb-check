mod support;

use std::fs;
use std::process::Command;

use support::{run_check, test_dir, write};

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

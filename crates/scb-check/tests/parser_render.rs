mod support;

use std::process::Command;

use support::{run_check, test_dir, write};

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

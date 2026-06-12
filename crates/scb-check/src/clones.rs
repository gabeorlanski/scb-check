use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use crate::model::{CloneBlock, Function};

#[derive(Debug, Clone)]
pub(crate) struct CloneCandidate {
    file: PathBuf,
    start_line: usize,
    end_line: usize,
    group_hash: String,
    first_lines: Vec<String>,
}

pub(crate) fn function_clone_candidate(
    function: &Function,
    fingerprint: &[String],
    lines: &[&str],
    sloc_lines: &BTreeSet<usize>,
) -> Option<CloneCandidate> {
    if fingerprint.len() < 2 {
        return None;
    }
    if !sloc_lines
        .iter()
        .any(|line| function.start_line <= *line && *line <= function.end_line)
    {
        return None;
    }

    let first_lines = lines
        .iter()
        .take(3)
        .map(|line| (*line).to_string())
        .collect();
    Some(CloneCandidate {
        file: function.file.clone(),
        start_line: function.start_line,
        end_line: function.end_line,
        group_hash: clone_group_hash(fingerprint),
        first_lines,
    })
}

pub(crate) fn detect_clones(candidates: Vec<CloneCandidate>) -> Vec<CloneBlock> {
    let mut groups: BTreeMap<String, Vec<CloneCandidate>> = BTreeMap::new();
    for candidate in candidates {
        groups
            .entry(candidate.group_hash.clone())
            .or_default()
            .push(candidate);
    }

    let mut clones = Vec::new();
    for (group_hash, mut group) in groups {
        if group.len() < 2 {
            continue;
        }
        group.sort_by(|left, right| {
            (left.file.as_os_str(), left.start_line, left.end_line).cmp(&(
                right.file.as_os_str(),
                right.start_line,
                right.end_line,
            ))
        });
        let instance_count = group.len();
        for candidate in group {
            clones.push(CloneBlock {
                file: candidate.file,
                start_line: candidate.start_line,
                end_line: candidate.end_line,
                group_hash: group_hash.clone(),
                instance_count,
                first_lines: candidate.first_lines,
            });
        }
    }
    clones.sort_by(|left, right| {
        (left.file.as_os_str(), left.start_line, left.end_line).cmp(&(
            right.file.as_os_str(),
            right.start_line,
            right.end_line,
        ))
    });
    clones
}

fn clone_group_hash(body_lines: &[String]) -> String {
    blake3::hash(body_lines.join("\n").as_bytes())
        .to_hex()
        .to_string()
}

#[cfg(test)]
mod tests {
    use crate::render::{render_human, render_json};
    use crate::test_support::{analyze_dir, test_dir, write};

    #[test]
    fn duplicate_python_and_rust_function_bodies_contribute_clone_loc() {
        let root = test_dir();
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

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");
        let human = render_human(&report, None, 1);

        assert!(report.has_findings());
        assert_eq!(report.clones.len(), 4);
        assert!(report.clone_loc > 0);
        assert!(report.verbosity_flagged_loc > 0);
        assert_eq!(human.matches("duplicate-structure:").count(), 2);
        assert!(human.contains("┌─"));
        assert!(human.contains("│"));
        assert!(human.contains("sample.py:1"));
        assert!(human.contains("sample.rs:1"));

        let json = render_json(&report);
        assert!(json.contains("\"clone_loc\":"));
        assert!(!json.contains("\"clone_loc\":0"));
        assert!(!json.contains("\"verbosity_flagged_loc\":0"));

        let filtered = render_human(&report, Some(6), 1);
        assert!(!filtered.contains("duplicate-structure:"));
    }

    #[test]
    fn clone_fingerprints_preserve_operator_differences() {
        let root = test_dir();
        write(
            &root.join("sample.py"),
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
            &root.join("sample.rs"),
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

        let report = analyze_dir(&root, true, false, None).expect("analysis should succeed");

        assert_eq!(report.clone_loc, 0);
        assert_eq!(report.verbosity_flagged_loc, 0);
    }
}

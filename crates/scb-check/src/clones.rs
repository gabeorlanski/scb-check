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

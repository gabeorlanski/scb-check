use std::collections::BTreeMap;
use std::path::Path;

use crate::model::{AstGrepFinding, CloneBlock, Function, Report, StructuralFinding};
use serde_json::json;

pub fn render_json(report: &Report) -> String {
    json!({
        "verbosity": json_number(report.verbosity()),
        "erosion": json_number(report.erosion()),
        "cog_erosion": json_number(report.cog_erosion()),
        "files_scanned": report.files_scanned,
        "total_loc": report.total_loc,
        "verbosity_flagged_loc": report.verbosity_flagged_loc,
        "clone_loc": report.clone_loc,
        "ast_grep_flagged_loc": report.ast_grep_flagged_loc,
        "structural_rule_loc": report.structural_rule_loc,
        "structural_rule_findings": report.structural_rule_findings,
        "total_functions": report.total_functions,
        "high_cc_functions": report.high_cc_functions,
        "high_cog_functions": report.high_cog_functions,
        "total_mass": json_number(report.total_mass),
        "high_cc_mass": json_number(report.high_cc_mass),
        "total_cog_mass": json_number(report.total_cog_mass),
        "high_cog_mass": json_number(report.high_cog_mass),
        "syntax_tree_count": report.syntax_tree_count(),
        "syntax_node_count": report.syntax_node_count(),
        "syntax_by_language": syntax_by_language(report),
    })
    .to_string()
}

fn json_number(value: f64) -> f64 {
    if !value.is_finite() || value.abs() < f64::EPSILON {
        0.0
    } else {
        value
    }
}

pub fn render_human(
    report: &Report,
    min_duplicate_lines: Option<usize>,
    context_lines: usize,
) -> String {
    let mut entries = Vec::new();
    let source_index = SourceIndex::new(report);
    append_clone_entries(&mut entries, report, min_duplicate_lines);
    append_ast_grep_entries(&mut entries, report, &source_index, context_lines);
    append_structural_entries(&mut entries, report, &source_index, context_lines);
    append_complexity_entries(&mut entries, report, &source_index, context_lines);
    entries.sort_by(|left, right| left.key.cmp(&right.key));
    entries
        .into_iter()
        .map(|entry| entry.text)
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn append_clone_entries(
    entries: &mut Vec<RenderedEntry>,
    report: &Report,
    min_duplicate_lines: Option<usize>,
) {
    for group in clone_groups(&report.clones) {
        let line_count = clone_line_count(group.anchor());
        if min_duplicate_lines.is_some_and(|minimum| line_count < minimum) {
            continue;
        }
        entries.push(RenderedEntry {
            key: render_key(&group.anchor().file, group.anchor().start_line, 0),
            text: render_clone_group(&group, line_count),
        });
    }
}

fn append_ast_grep_entries(
    entries: &mut Vec<RenderedEntry>,
    report: &Report,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
) {
    for finding in &report.ast_grep_findings {
        entries.push(RenderedEntry {
            key: render_key(&finding.file, finding.start_line, 1),
            text: render_ast_grep(finding, source_index, context_lines),
        });
    }
}

fn append_structural_entries(
    entries: &mut Vec<RenderedEntry>,
    report: &Report,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
) {
    for finding in &report.structural_findings {
        entries.push(RenderedEntry {
            key: render_key(&finding.file, finding.start_line, 2),
            text: render_structural(finding, source_index, context_lines),
        });
    }
}

fn append_complexity_entries(
    entries: &mut Vec<RenderedEntry>,
    report: &Report,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
) {
    for function in report
        .functions
        .iter()
        .filter(|function| function.is_high_cc())
    {
        entries.push(RenderedEntry {
            key: render_key(&function.file, function.start_line, 3),
            text: render_complexity(function, source_index, context_lines, false),
        });
    }
    for function in report
        .functions
        .iter()
        .filter(|function| function.is_high_cog())
    {
        entries.push(RenderedEntry {
            key: render_key(&function.file, function.start_line, 4),
            text: render_complexity(function, source_index, context_lines, true),
        });
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct RenderKey {
    path: String,
    line: usize,
    kind_rank: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RenderedEntry {
    key: RenderKey,
    text: String,
}

fn render_key(file: &Path, line: usize, kind_rank: u8) -> RenderKey {
    RenderKey {
        path: display_path(file),
        line,
        kind_rank,
    }
}

fn syntax_by_language(report: &Report) -> serde_json::Value {
    let entries = report.syntax_by_language.iter().map(|summary| {
        (
            summary.language.as_str().to_string(),
            json!({
                "tree_count": summary.tree_count,
                "node_count": summary.node_count,
            }),
        )
    });
    entries.collect::<serde_json::Map<_, _>>().into()
}

fn clone_groups(clones: &[CloneBlock]) -> Vec<CloneGroup> {
    let mut clones = clones.to_vec();
    clones.sort_by(|left, right| {
        (
            left.group_hash.as_str(),
            left.file.as_os_str(),
            left.start_line,
        )
            .cmp(&(
                right.group_hash.as_str(),
                right.file.as_os_str(),
                right.start_line,
            ))
    });

    let mut groups: Vec<CloneGroup> = Vec::new();
    for clone in clones {
        if groups
            .last()
            .is_some_and(|group| group.group_hash() == clone.group_hash)
        {
            if let Some(group) = groups.last_mut() {
                group.rest.push(clone);
            }
        } else {
            groups.push(CloneGroup::new(clone));
        }
    }
    groups.sort_by(|left, right| {
        let left_anchor = left.anchor();
        let right_anchor = right.anchor();
        (left_anchor.file.as_os_str(), left_anchor.start_line)
            .cmp(&(right_anchor.file.as_os_str(), right_anchor.start_line))
    });
    groups
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CloneGroup {
    anchor: CloneBlock,
    rest: Vec<CloneBlock>,
}

impl CloneGroup {
    const fn new(anchor: CloneBlock) -> Self {
        Self {
            anchor,
            rest: Vec::new(),
        }
    }

    const fn anchor(&self) -> &CloneBlock {
        &self.anchor
    }

    fn group_hash(&self) -> &str {
        &self.anchor.group_hash
    }

    fn iter(&self) -> impl Iterator<Item = &CloneBlock> {
        std::iter::once(&self.anchor).chain(self.rest.iter())
    }
}

fn render_clone_group(group: &CloneGroup, line_count: usize) -> String {
    let anchor = group.anchor();
    let line_number_width = group
        .iter()
        .map(|clone| clone.end_line.to_string().len())
        .max()
        .unwrap_or(1);
    let pad = " ".repeat(line_number_width);
    let mut lines = vec![format!(
        "duplicate-structure: duplicated block ({} lines, {} instances)",
        line_count, anchor.instance_count
    )];
    for (index, clone) in group.iter().enumerate() {
        if index > 0 {
            lines.push(format!("{pad} ┆"));
        }
        lines.push(format!(
            "{pad} ┌─ {}:{}",
            display_path(&clone.file),
            clone.start_line
        ));
        lines.push(format!("{pad} │"));
        for (offset, text) in clone.first_lines.iter().enumerate() {
            lines.push(format!(
                "{:>line_number_width$} │ {}",
                clone.start_line + offset,
                text
            ));
        }
        lines.push(format!("{pad} │"));
    }
    lines.join("\n")
}

const fn clone_line_count(clone: &CloneBlock) -> usize {
    clone.sloc
}

fn render_ast_grep(
    finding: &AstGrepFinding,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
) -> String {
    let message = if finding.message.trim().is_empty() {
        "matches slop pattern"
    } else {
        finding.message.trim()
    };
    let mut lines = vec![format!(
        "{}[{}]: {}\n  --> {}:{}:{}",
        finding.severity,
        finding.rule_id,
        message,
        display_path(&finding.file),
        finding.start_line,
        finding.start_col + 1
    )];
    lines.extend(source_block(
        source_index,
        &finding.file,
        finding.start_line,
        finding.end_line,
        context_lines,
    ));
    lines.join("\n")
}

fn render_structural(
    finding: &StructuralFinding,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
) -> String {
    let mut lines = vec![format!(
        "{}[{}]: {}\n  --> {}:{}",
        finding.rule_id,
        finding.severity,
        finding.message,
        display_path(&finding.file),
        finding.start_line
    )];
    lines.extend(source_block(
        source_index,
        &finding.file,
        finding.start_line,
        finding.end_line,
        context_lines,
    ));
    lines.join("\n")
}

fn render_complexity(
    function: &Function,
    source_index: &SourceIndex<'_>,
    context_lines: usize,
    cognitive: bool,
) -> String {
    let mut lines = if cognitive {
        vec![format!(
            "cog_erosion: function `{}` exceeds cognitive complexity threshold\n  --> {}:{}",
            function.name,
            display_path(&function.file),
            function.start_line,
        )]
    } else {
        vec![format!(
            "erosion: function `{}` exceeds complexity threshold\n  --> {}:{}",
            function.name,
            display_path(&function.file),
            function.start_line,
        )]
    };
    lines.extend(source_block(
        source_index,
        &function.file,
        function.start_line,
        function.start_line,
        context_lines,
    ));
    if cognitive {
        lines.push(format!(
            "  = cognitive complexity: {}, sloc: {} (threshold: cognitive complexity > 10)",
            function.cognitive, function.sloc
        ));
    } else {
        lines.push(format!(
            "  = complexity: {}, sloc: {} (threshold: complexity > 10)",
            function.cyclomatic, function.sloc
        ));
    }
    lines.join("\n")
}

fn source_block(
    source_index: &SourceIndex<'_>,
    file: &Path,
    start_line: usize,
    end_line: usize,
    context_lines: usize,
) -> Vec<String> {
    let Some(source_lines) = source_index.lines(file) else {
        return Vec::new();
    };
    let first_line = start_line.saturating_sub(context_lines).max(1);
    let last_line = end_line
        .max(start_line)
        .saturating_add(context_lines)
        .min(source_lines.len());
    let width = last_line.to_string().len();
    let mut rendered = Vec::new();
    for line_number in first_line..=last_line {
        let text = source_lines
            .get(line_number.saturating_sub(1))
            .map(|line| line.trim_end())
            .unwrap_or_default();
        rendered.push(format!("{line_number:>width$} | {text}"));
    }
    rendered
}

#[derive(Debug)]
struct SourceIndex<'a> {
    by_file: BTreeMap<&'a Path, &'a [String]>,
}

impl<'a> SourceIndex<'a> {
    fn new(report: &'a Report) -> Self {
        let by_file = report
            .source_lines
            .iter()
            .map(|source| (source.file.as_path(), source.lines.as_slice()))
            .collect();
        Self { by_file }
    }

    fn lines(&self, file: &Path) -> Option<&'a [String]> {
        let lines = self.by_file.get(file).copied()?;
        (!lines.is_empty()).then_some(lines)
    }
}

fn display_path(path: &Path) -> String {
    let Ok(cwd) = std::env::current_dir() else {
        return path.display().to_string();
    };
    path.strip_prefix(cwd)
        .unwrap_or(path)
        .to_string_lossy()
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::render_human;
    use crate::test_support::{analyze_dir, test_dir, write};

    #[test]
    fn human_output_orders_mixed_findings_and_renders_context_lines() {
        let root = test_dir();
        let config = root.join("scb-check.toml");
        write(&config, "context = 1\n");
        write(
            &root.join("sample.py"),
            r"
def _identity(value):
    return value

def noisy(items):
    for index in range(len(items)):
        print(items[index])
",
        );

        let report =
            analyze_dir(&root, false, false, Some(&config)).expect("analysis should succeed");
        let rendered = render_human(&report, None, 1);

        let structural_index = rendered
            .find("trivial-wrapper[warning]")
            .expect("structural finding should render");
        let ast_index = rendered
            .find("warning[for-range-len]")
            .expect("ast-grep finding should render");
        assert!(structural_index < ast_index);
        assert!(rendered.contains("1 | def _identity(value):"));
        assert!(rendered.contains("2 |     return value"));
        assert!(rendered.contains("4 | def noisy(items):"));
        assert!(rendered.contains("5 |     for index in range(len(items)):"));
        assert!(rendered.contains("6 |         print(items[index])"));
    }
}

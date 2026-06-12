use std::path::{Path, PathBuf};

use globset::{Glob, GlobSet, GlobSetBuilder};
use ignore::{DirEntry, WalkBuilder};

use crate::config::Config;
use crate::model::{Language, SourceFile};

const DEFAULT_EXCLUDED_DIRS: &[&str] = &[
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "target",
];

pub(crate) fn discover_sources(
    path: &Path,
    config: &Config,
    include_all: bool,
) -> Result<Vec<SourceFile>, String> {
    if !path.exists() {
        return Err(format!("path does not exist: {}", path.display()));
    }

    if path.is_file() {
        return discover_explicit_file(path);
    }

    let root = absolute(path)?;
    let exclude_set = user_exclude_set(&config.exclude)?;
    let mut files = Vec::new();
    for entry in source_walk(&root, include_all) {
        let entry = entry.map_err(|error| error.to_string())?;
        push_source_entry(entry.path(), config, &exclude_set, &mut files)?;
    }
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(files)
}

fn discover_explicit_file(path: &Path) -> Result<Vec<SourceFile>, String> {
    let language = language_for_path(path)
        .ok_or_else(|| format!("not a supported source file: {}", path.display()))?;
    Ok(vec![SourceFile {
        path: absolute(path)?,
        language,
    }])
}

fn source_walk(
    root: &Path,
    include_all: bool,
) -> impl Iterator<Item = Result<DirEntry, ignore::Error>> {
    let mut builder = WalkBuilder::new(root);
    builder
        .follow_links(false)
        .hidden(false)
        .ignore(!include_all)
        .require_git(false)
        .parents(!include_all)
        .git_ignore(!include_all)
        .git_global(false)
        .git_exclude(false)
        .filter_entry(is_default_discoverable_entry);
    builder.build()
}

fn is_default_discoverable_entry(entry: &DirEntry) -> bool {
    entry.depth() == 0 || is_default_discoverable_path(entry.path())
}

fn is_default_discoverable_path(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_none_or(|name| !DEFAULT_EXCLUDED_DIRS.contains(&name))
}

fn push_source_entry(
    path: &Path,
    config: &Config,
    exclude_set: &GlobSet,
    files: &mut Vec<SourceFile>,
) -> Result<(), String> {
    let Some(language) = language_for_path(path) else {
        return Ok(());
    };
    if !is_user_excluded(path, config, exclude_set) {
        files.push(SourceFile {
            path: absolute(path)?,
            language,
        });
    }
    Ok(())
}

fn language_for_path(path: &Path) -> Option<Language> {
    match path.extension().and_then(|extension| extension.to_str()) {
        Some("py" | "pyw") => Some(Language::Python),
        Some("rs") => Some(Language::Rust),
        _ => None,
    }
}

fn absolute(path: &Path) -> Result<PathBuf, String> {
    path.canonicalize()
        .map_err(|error| format!("failed to resolve {}: {error}", path.display()))
}

fn user_exclude_set(patterns: &[String]) -> Result<GlobSet, String> {
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let glob = Glob::new(pattern)
            .map_err(|error| format!("invalid exclude pattern {pattern:?}: {error}"))?;
        builder.add(glob);
    }
    builder
        .build()
        .map_err(|error| format!("invalid exclude patterns: {error}"))
}

fn is_user_excluded(path: &Path, config: &Config, exclude_set: &GlobSet) -> bool {
    let relative = path.strip_prefix(&config.base_dir).unwrap_or(path);
    exclude_set.is_match(relative)
}

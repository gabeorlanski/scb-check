use std::path::{Path, PathBuf};

use globset::{Glob, GlobSet, GlobSetBuilder};
use ignore::{DirEntry, WalkBuilder};
use thiserror::Error;

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

#[derive(Debug, Error)]
pub enum WalkError {
    #[error("path does not exist: {}", path.display())]
    MissingPath { path: PathBuf },
    #[error("not a supported source file: {}", path.display())]
    UnsupportedFile { path: PathBuf },
    #[error("failed to resolve {}: {source}", path.display())]
    ResolvePath {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to walk sources: {source}")]
    Walk {
        #[source]
        source: ignore::Error,
    },
    #[error("invalid exclude pattern {pattern:?}: {source}")]
    InvalidExcludePattern {
        pattern: String,
        #[source]
        source: globset::Error,
    },
    #[error("invalid exclude patterns: {source}")]
    InvalidExcludePatterns {
        #[source]
        source: globset::Error,
    },
}

/// Discover supported source files below a path after applying configuration exclusions.
///
/// Returned records own canonical paths because parsing and reporting outlive the borrowed CLI
/// path and configuration values used during discovery.
pub fn discover_sources(
    path: &Path,
    config: &Config,
    include_all: bool,
) -> Result<Vec<SourceFile>, WalkError> {
    if !path.exists() {
        return Err(WalkError::MissingPath {
            path: path.to_path_buf(),
        });
    }

    if path.is_file() {
        return discover_explicit_file(path);
    }

    let root = absolute(path)?;
    let exclude_set = user_exclude_set(&config.exclude)?;
    let mut files = Vec::new();
    for entry in source_walk(&root, include_all) {
        let entry = entry.map_err(|source| WalkError::Walk { source })?;
        push_source_entry(entry.path(), config, &exclude_set, &mut files)?;
    }
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(files)
}

fn discover_explicit_file(path: &Path) -> Result<Vec<SourceFile>, WalkError> {
    let language = language_for_path(path).ok_or_else(|| WalkError::UnsupportedFile {
        path: path.to_path_buf(),
    })?;
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
) -> Result<(), WalkError> {
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

fn absolute(path: &Path) -> Result<PathBuf, WalkError> {
    path.canonicalize()
        .map_err(|source| WalkError::ResolvePath {
            path: path.to_path_buf(),
            source,
        })
}

fn user_exclude_set(patterns: &[String]) -> Result<GlobSet, WalkError> {
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let glob = Glob::new(pattern).map_err(|source| WalkError::InvalidExcludePattern {
            pattern: pattern.clone(),
            source,
        })?;
        builder.add(glob);
    }
    builder
        .build()
        .map_err(|source| WalkError::InvalidExcludePatterns { source })
}

fn is_user_excluded(path: &Path, config: &Config, exclude_set: &GlobSet) -> bool {
    let relative = path.strip_prefix(&config.base_dir).unwrap_or(path);
    exclude_set.is_match(relative)
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::discover_sources;
    use crate::config::Config;
    use crate::model::Language;
    use crate::test_support::{test_dir, write};

    #[test]
    fn ignores_non_cutover_languages_in_directory_scan() {
        let root = test_dir();
        write(&root.join("sample.py"), "value = 1\n");
        write(&root.join("sample.rs"), "fn value() -> i32 {\n    1\n}\n");
        write(&root.join("sample.js"), "function value() { return 1 }\n");
        write(&root.join("sample.ts"), "const value: number = 1\n");
        write(&root.join("sample.go"), "package main\n");
        let config = Config::default_for(&root);

        let sources = discover_sources(&root, &config, false).expect("discovery should succeed");

        assert_eq!(sources.len(), 2);
        assert!(
            sources
                .iter()
                .any(|source| source.language == Language::Python)
        );
        assert!(
            sources
                .iter()
                .any(|source| source.language == Language::Rust)
        );
    }

    #[test]
    fn applies_scb_config_excludes() {
        let root = test_dir();
        fs::create_dir(root.join("generated")).expect("generated dir should be created");
        write(&root.join("keep.py"), "value = 1\n");
        write(&root.join("generated").join("skip.py"), "value = 2\n");
        write(&root.join("keep.rs"), "fn value() -> i32 {\n    1\n}\n");
        let mut config = Config::default_for(&root);
        config.base_dir = root
            .canonicalize()
            .expect("test root should be canonicalizable");
        config.exclude = vec!["generated/**".to_string()];

        let sources = discover_sources(&root, &config, false).expect("discovery should succeed");

        assert_eq!(sources.len(), 2);
    }

    #[test]
    fn include_all_includes_gitignored_but_not_default_excluded_dirs() {
        let root = test_dir();
        write(&root.join(".gitignore"), "ignored.py\n");
        fs::create_dir(root.join("node_modules")).expect("node_modules dir should be created");
        write(&root.join("keep.py"), "value = 1\n");
        write(&root.join("ignored.py"), "value = 2\n");
        write(&root.join("node_modules").join("skip.py"), "value = 3\n");
        let config = Config::default_for(&root);

        let default_sources =
            discover_sources(&root, &config, false).expect("discovery should succeed");
        let include_all_sources =
            discover_sources(&root, &config, true).expect("discovery should succeed");

        assert_eq!(default_sources.len(), 1);
        assert_eq!(include_all_sources.len(), 2);
    }

    #[test]
    fn explicit_unsupported_file_is_usage_error() {
        let root = test_dir();
        let source = root.join("sample.go");
        write(&source, "package main\n");
        let config = Config::default_for(&root);

        let error = discover_sources(&source, &config, false).expect_err("source should fail");

        assert!(error.to_string().contains("not a supported source file"));
    }
}

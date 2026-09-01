use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use thiserror::Error;
use toml::Value;
use toml::map::Map;

const DEFAULT_CONTEXT_LINES: usize = 1;
const DEFAULT_MAX_CALL_SITES: usize = 2;
const DEFAULT_MAX_FUNCTION_SLOC: usize = 5;
const DEFAULT_MAX_INLINE_CALLER_SLOC: usize = 50;
const DEFAULT_MAX_INLINE_CALLER_COMPLEXITY: usize = 10;
const DEFAULT_MAX_INLINE_CALLER_COGNITIVE_COMPLEXITY: usize = 10;
const DEFAULT_MAX_INLINE_CALL_NESTING: usize = 3;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub exclude: Vec<String>,
    pub base_dir: PathBuf,
    pub context_lines: usize,
    pub low_use_short_function: LowUseShortFunctionSettings,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LowUseShortFunctionSettings {
    pub enabled: bool,
    pub max_call_sites: usize,
    pub max_function_sloc: usize,
    pub max_inline_caller_sloc: usize,
    pub max_inline_caller_complexity: usize,
    pub max_inline_caller_cognitive_complexity: usize,
    pub max_inline_call_nesting: usize,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("config path does not exist: {}", path.display())]
    MissingPath { path: PathBuf },
    #[error("failed to resolve {}: {source}", path.display())]
    ResolvePath {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to resolve config directory: {source}")]
    ResolveConfigDirectory {
        #[source]
        source: std::io::Error,
    },
    #[error("{}: failed to read config", path.display())]
    Read {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("{}: failed to parse config: {source}", path.display())]
    ParseToml {
        path: PathBuf,
        #[source]
        source: toml::de::Error,
    },
    #[error("{}: failed to parse config: {source}", path.display())]
    Deserialize {
        path: PathBuf,
        #[source]
        source: toml::de::Error,
    },
    #[error("{key} must be >= {minimum}")]
    ValueBelowMinimum { key: &'static str, minimum: usize },
}

#[derive(Debug, Deserialize)]
#[serde(default, rename_all = "kebab-case", deny_unknown_fields)]
struct RawScbConfig {
    exclude: Vec<String>,
    context: usize,
    low_use_short_function: RawLowUseShortFunctionSettings,
}

#[derive(Debug, Deserialize)]
#[serde(default, rename_all = "kebab-case", deny_unknown_fields)]
struct RawLowUseShortFunctionSettings {
    enabled: bool,
    max_call_sites: usize,
    max_function_sloc: usize,
    max_inline_caller_sloc: usize,
    max_inline_caller_complexity: usize,
    max_inline_caller_cognitive_complexity: usize,
    max_inline_call_nesting: usize,
}

impl Default for RawScbConfig {
    fn default() -> Self {
        Self {
            exclude: Vec::new(),
            context: DEFAULT_CONTEXT_LINES,
            low_use_short_function: RawLowUseShortFunctionSettings::default(),
        }
    }
}

impl Default for RawLowUseShortFunctionSettings {
    fn default() -> Self {
        Self {
            enabled: false,
            max_call_sites: DEFAULT_MAX_CALL_SITES,
            max_function_sloc: DEFAULT_MAX_FUNCTION_SLOC,
            max_inline_caller_sloc: DEFAULT_MAX_INLINE_CALLER_SLOC,
            max_inline_caller_complexity: DEFAULT_MAX_INLINE_CALLER_COMPLEXITY,
            max_inline_caller_cognitive_complexity: DEFAULT_MAX_INLINE_CALLER_COGNITIVE_COMPLEXITY,
            max_inline_call_nesting: DEFAULT_MAX_INLINE_CALL_NESTING,
        }
    }
}

impl Default for LowUseShortFunctionSettings {
    fn default() -> Self {
        RawLowUseShortFunctionSettings::default().into()
    }
}

impl From<RawLowUseShortFunctionSettings> for LowUseShortFunctionSettings {
    fn from(raw: RawLowUseShortFunctionSettings) -> Self {
        Self {
            enabled: raw.enabled,
            max_call_sites: raw.max_call_sites,
            max_function_sloc: raw.max_function_sloc,
            max_inline_caller_sloc: raw.max_inline_caller_sloc,
            max_inline_caller_complexity: raw.max_inline_caller_complexity,
            max_inline_caller_cognitive_complexity: raw.max_inline_caller_cognitive_complexity,
            max_inline_call_nesting: raw.max_inline_call_nesting,
        }
    }
}

impl Config {
    /// Create the implicit configuration used when no configuration file is discovered.
    ///
    /// The base directory is copied into owned storage because the configuration survives the
    /// borrowed current-working-directory value supplied at the CLI boundary.
    pub fn default_for(cwd: &Path) -> Self {
        Self {
            exclude: Vec::new(),
            base_dir: cwd.to_path_buf(),
            context_lines: DEFAULT_CONTEXT_LINES,
            low_use_short_function: LowUseShortFunctionSettings::default(),
        }
    }
}

/// Load an explicit configuration file or discover one from the current directory upward.
pub fn load_config(override_path: Option<&Path>, cwd: &Path) -> Result<Config, ConfigError> {
    if let Some(path) = override_path {
        if !path.exists() {
            return Err(ConfigError::MissingPath {
                path: path.to_path_buf(),
            });
        }
        return parse_config_file(path);
    }

    let Some(path) = discover_config(cwd)? else {
        return Ok(Config::default_for(cwd));
    };
    parse_config_file(&path)
}

fn discover_config(start: &Path) -> Result<Option<PathBuf>, ConfigError> {
    let mut current = start
        .canonicalize()
        .map_err(|source| ConfigError::ResolvePath {
            path: start.to_path_buf(),
            source,
        })?;
    loop {
        if let Some(path) = config_file_in(&current)? {
            return Ok(Some(path));
        }
        let Some(parent) = next_config_parent(&current) else {
            return Ok(None);
        };
        current = parent;
    }
}

fn config_file_in(directory: &Path) -> Result<Option<PathBuf>, ConfigError> {
    let scb_check_file = directory.join("scb-check.toml");
    if scb_check_file.is_file() {
        return Ok(Some(scb_check_file));
    }

    let pyproject = directory.join("pyproject.toml");
    if pyproject.is_file() && pyproject_has_compatible_config(&pyproject)? {
        return Ok(Some(pyproject));
    }

    Ok(None)
}

fn next_config_parent(directory: &Path) -> Option<PathBuf> {
    if directory.join(".git").is_dir() {
        return None;
    }
    let parent = directory.parent()?;
    (parent != directory).then(|| parent.to_path_buf())
}

fn pyproject_has_compatible_config(path: &Path) -> Result<bool, ConfigError> {
    let raw = read_config(path)?;
    let document = parse_toml(path, &raw)?;
    Ok(value_at(&document, &["tool", "scb-check"]).is_some()
        || table_at(&document, &["tool", "ruff"]).is_some()
        || table_at(&document, &["tool", "ty", "src"]).is_some())
}

fn parse_config_file(path: &Path) -> Result<Config, ConfigError> {
    let raw = read_config(path)?;
    let document = parse_toml(path, &raw)?;
    let base_dir = path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()
        .map_err(|source| ConfigError::ResolveConfigDirectory { source })?;

    if !is_pyproject(path) {
        return parse_scb_config(path, document, base_dir);
    }

    let mut config = parse_pyproject_config(path, &document, base_dir)?;
    config.exclude.extend(python_tool_excludes(&document));
    dedupe(&mut config.exclude);
    Ok(config)
}

fn is_pyproject(path: &Path) -> bool {
    path.file_name().and_then(|name| name.to_str()) == Some("pyproject.toml")
}

fn parse_pyproject_config(
    path: &Path,
    document: &Value,
    base_dir: PathBuf,
) -> Result<Config, ConfigError> {
    if let Some(scb_value) = value_at(document, &["tool", "scb-check"]) {
        parse_scb_config(path, scb_value.clone(), base_dir)
    } else {
        Ok(Config {
            exclude: Vec::new(),
            base_dir,
            context_lines: DEFAULT_CONTEXT_LINES,
            low_use_short_function: LowUseShortFunctionSettings::default(),
        })
    }
}

fn parse_scb_config(path: &Path, value: Value, base_dir: PathBuf) -> Result<Config, ConfigError> {
    let raw = value
        .try_into::<RawScbConfig>()
        .map_err(|source| ConfigError::Deserialize {
            path: path.to_path_buf(),
            source,
        })?;
    let low_use_short_function = low_use_settings(&raw.low_use_short_function)?;
    Ok(Config {
        exclude: norm_patterns(raw.exclude),
        base_dir,
        context_lines: raw.context,
        low_use_short_function,
    })
}

fn low_use_settings(
    raw: &RawLowUseShortFunctionSettings,
) -> Result<LowUseShortFunctionSettings, ConfigError> {
    Ok(LowUseShortFunctionSettings {
        enabled: raw.enabled,
        max_call_sites: min_int_value("max-call-sites", raw.max_call_sites, 1)?,
        max_function_sloc: min_int_value("max-function-sloc", raw.max_function_sloc, 1)?,
        max_inline_caller_sloc: min_int_value(
            "max-inline-caller-sloc",
            raw.max_inline_caller_sloc,
            1,
        )?,
        max_inline_caller_complexity: min_int_value(
            "max-inline-caller-complexity",
            raw.max_inline_caller_complexity,
            1,
        )?,
        max_inline_caller_cognitive_complexity: min_int_value(
            "max-inline-caller-cognitive-complexity",
            raw.max_inline_caller_cognitive_complexity,
            0,
        )?,
        max_inline_call_nesting: min_int_value(
            "max-inline-call-nesting",
            raw.max_inline_call_nesting,
            0,
        )?,
    })
}

fn python_tool_excludes(document: &Value) -> Vec<String> {
    let mut patterns = Vec::new();
    if let Some(ruff) = table_at(document, &["tool", "ruff"]) {
        if let Some(exclude) = tool_string_list_value(ruff, "exclude") {
            patterns.extend(norm_patterns(exclude));
        }
        if let Some(exclude) = tool_string_list_value(ruff, "extend-exclude") {
            patterns.extend(norm_patterns(exclude));
        }
    }
    if let Some(ty) = table_at(document, &["tool", "ty", "src"])
        && let Some(exclude) = tool_string_list_value(ty, "exclude")
    {
        patterns.extend(norm_patterns(exclude));
    }
    patterns
}

fn read_config(path: &Path) -> Result<String, ConfigError> {
    fs::read_to_string(path).map_err(|source| ConfigError::Read {
        path: path.to_path_buf(),
        source,
    })
}

fn parse_toml(path: &Path, raw: &str) -> Result<Value, ConfigError> {
    toml::from_str::<Value>(raw).map_err(|source| ConfigError::ParseToml {
        path: path.to_path_buf(),
        source,
    })
}

fn table_at<'a>(document: &'a Value, path: &[&str]) -> Option<&'a Map<String, Value>> {
    value_at(document, path)?.as_table()
}

fn value_at<'a>(document: &'a Value, path: &[&str]) -> Option<&'a Value> {
    let mut current = document;
    for key in path {
        current = current.get(*key)?;
    }
    Some(current)
}

fn tool_string_list_value(table: &Map<String, Value>, key: &str) -> Option<Vec<String>> {
    let array = table.get(key)?.as_array()?;
    array
        .iter()
        .map(|item| item.as_str().map(ToString::to_string))
        .collect()
}

const fn min_int_value(
    key: &'static str,
    value: usize,
    minimum: usize,
) -> Result<usize, ConfigError> {
    if value < minimum {
        return Err(ConfigError::ValueBelowMinimum { key, minimum });
    }
    Ok(value)
}

fn norm_patterns(patterns: Vec<String>) -> Vec<String> {
    let mut normalized = Vec::new();
    for pattern in patterns {
        let pattern = pattern.trim().replace('\\', "/");
        let pattern = normalized_pattern_text(&pattern);
        normalized.extend(norm_pattern_entries(&pattern));
    }
    dedupe(&mut normalized);
    normalized
}

fn normalized_pattern_text(pattern: &str) -> String {
    pattern
        .strip_prefix("./")
        .unwrap_or(pattern)
        .trim_start_matches('/')
        .to_string()
}

fn norm_pattern_entries(pattern: &str) -> Vec<String> {
    if pattern.is_empty() {
        Vec::new()
    } else if pattern.ends_with('/') {
        vec![format!("{}**", pattern)]
    } else if is_glob_pattern(pattern) {
        vec![pattern.to_string()]
    } else {
        vec![pattern.to_string(), format!("{pattern}/**")]
    }
}

fn is_glob_pattern(pattern: &str) -> bool {
    pattern.contains('*') || pattern.contains('?') || pattern.contains('[')
}

fn dedupe(values: &mut Vec<String>) {
    let mut index = 0;
    while index < values.len() {
        if values[..index].contains(&values[index]) {
            values.remove(index);
        } else {
            index += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::load_config;
    use crate::test_support::{test_dir, write};

    fn config_error_for(content: &str) -> String {
        let root = test_dir();
        let config_path = root.join("scb-check.toml");
        write(&config_path, content);

        load_config(Some(&config_path), &root)
            .expect_err("config should fail")
            .to_string()
    }

    #[test]
    fn pyproject_tool_excludes_and_low_use_settings_are_supported() {
        let root = test_dir();
        let config_path = root.join("pyproject.toml");
        write(
            &config_path,
            r#"
[tool.ruff]
exclude = ["vendor/"]

[tool.ty.src]
exclude = ["fixtures/"]

[tool.scb-check.low-use-short-function]
enabled = true
"#,
        );

        let config = load_config(Some(&config_path), &root).expect("config should parse");

        assert!(config.low_use_short_function.enabled);
        assert_eq!(config.exclude, ["vendor/**", "fixtures/**"]);
    }

    #[test]
    fn config_rejects_unknown_keys() {
        for (content, unknown_key) in [
            (
                "low-use-short-function-extra = 7\n",
                "low-use-short-function-extra",
            ),
            (
                "[low-use-short-function]\nenabled = true\nmax-call-sites-extra = 7\n",
                "max-call-sites-extra",
            ),
        ] {
            let error = config_error_for(content);

            assert!(error.contains(unknown_key));
        }
    }

    #[test]
    fn explicit_pyproject_rejects_non_table_scb_check_config() {
        let root = test_dir();
        let config_path = root.join("pyproject.toml");
        write(&config_path, "tool.scb-check = \"bad\"\n");

        let error = load_config(Some(&config_path), &root).expect_err("invalid config should fail");

        assert!(error.to_string().contains("failed to parse config"));
    }
}

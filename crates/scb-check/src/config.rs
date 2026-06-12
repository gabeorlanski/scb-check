use std::fs;
use std::path::{Path, PathBuf};

use toml::Value;
use toml::map::Map;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Config {
    pub exclude: Vec<String>,
    pub base_dir: PathBuf,
    pub context_lines: usize,
    pub low_use_short_function: LowUseShortFunctionSettings,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct LowUseShortFunctionSettings {
    pub enabled: bool,
    pub max_call_sites: usize,
    pub max_function_sloc: usize,
    pub max_inline_caller_sloc: usize,
    pub max_inline_caller_complexity: usize,
    pub max_inline_caller_cognitive_complexity: usize,
    pub max_inline_call_nesting: usize,
}

impl Default for LowUseShortFunctionSettings {
    fn default() -> Self {
        Self {
            enabled: false,
            max_call_sites: 2,
            max_function_sloc: 5,
            max_inline_caller_sloc: 50,
            max_inline_caller_complexity: 10,
            max_inline_caller_cognitive_complexity: 10,
            max_inline_call_nesting: 3,
        }
    }
}

impl Config {
    pub(crate) fn default_for(cwd: &Path) -> Self {
        Self {
            exclude: Vec::new(),
            base_dir: cwd.to_path_buf(),
            context_lines: 1,
            low_use_short_function: LowUseShortFunctionSettings::default(),
        }
    }
}

pub(crate) fn load_config(override_path: Option<&Path>, cwd: &Path) -> Result<Config, String> {
    if let Some(path) = override_path {
        if !path.exists() {
            return Err(format!("config path does not exist: {}", path.display()));
        }
        return parse_config_file(path);
    }

    let Some(path) = discover_config(cwd)? else {
        return Ok(Config::default_for(cwd));
    };
    parse_config_file(&path)
}

fn discover_config(start: &Path) -> Result<Option<PathBuf>, String> {
    let mut current = start
        .canonicalize()
        .map_err(|error| format!("failed to resolve {}: {error}", start.display()))?;
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

fn config_file_in(directory: &Path) -> Result<Option<PathBuf>, String> {
    let scb_check_file = directory.join("scb-check.toml");
    if scb_check_file.is_file() {
        return Ok(Some(scb_check_file));
    }

    let pyproject = directory.join("pyproject.toml");
    if pyproject.is_file() && has_config(&pyproject)? {
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

fn has_config(path: &Path) -> Result<bool, String> {
    let raw = read_config(path)?;
    let document = parse_toml(path, &raw)?;
    Ok(table_at(&document, &["tool", "scb-check"]).is_some()
        || table_at(&document, &["tool", "ruff"]).is_some()
        || table_at(&document, &["tool", "ty", "src"]).is_some())
}

fn parse_config_file(path: &Path) -> Result<Config, String> {
    let raw = read_config(path)?;
    let document = parse_toml(path, &raw)?;
    let base_dir = path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()
        .map_err(|error| format!("failed to resolve config directory: {error}"))?;

    if path.file_name().and_then(|name| name.to_str()) != Some("pyproject.toml") {
        return parse_scb_table(
            path,
            document.as_table(),
            table_at(&document, &["low-use-short-function"]),
            base_dir,
        );
    }

    let scb_table = table_at(&document, &["tool", "scb-check"]);
    let low_use_table = table_at(&document, &["tool", "scb-check", "low-use-short-function"]);
    let mut config = if scb_table.is_some() || low_use_table.is_some() {
        parse_scb_table(path, scb_table, low_use_table, base_dir)?
    } else {
        Config {
            exclude: Vec::new(),
            base_dir,
            context_lines: 1,
            low_use_short_function: LowUseShortFunctionSettings::default(),
        }
    };
    config.exclude.extend(tool_excludes(&document));
    dedupe(&mut config.exclude);
    Ok(config)
}

fn parse_scb_table(
    path: &Path,
    table: Option<&Map<String, Value>>,
    low_use_table: Option<&Map<String, Value>>,
    base_dir: PathBuf,
) -> Result<Config, String> {
    let allowed = ["exclude", "context"];
    for key in table_keys(table) {
        if !allowed.contains(&key.as_str()) && !key.starts_with("low-use-short-function") {
            return Err(format!("{}: unknown key: {key}", path.display()));
        }
    }

    let exclude = string_list_value(table, "exclude")?.map_or_else(Vec::new, norm_patterns);
    let context_lines = int_value(table, "context")?.unwrap_or(1);
    let low_use_short_function = low_use_settings(path, low_use_table)?;
    Ok(Config {
        exclude,
        base_dir,
        context_lines,
        low_use_short_function,
    })
}

fn low_use_settings(
    path: &Path,
    table: Option<&Map<String, Value>>,
) -> Result<LowUseShortFunctionSettings, String> {
    let Some(table) = table else {
        return Ok(LowUseShortFunctionSettings::default());
    };
    let allowed = [
        "enabled",
        "max-call-sites",
        "max-function-sloc",
        "max-inline-caller-sloc",
        "max-inline-caller-complexity",
        "max-inline-caller-cognitive-complexity",
        "max-inline-call-nesting",
    ];
    for key in table_keys(Some(table)) {
        if !allowed.contains(&key.as_str()) {
            return Err(format!(
                "{}: unknown low-use-short-function key: {key}",
                path.display()
            ));
        }
    }
    Ok(LowUseShortFunctionSettings {
        enabled: bool_value(table, "enabled")?.unwrap_or(false),
        max_call_sites: min_int_value(table, "max-call-sites", 2, 1)?,
        max_function_sloc: min_int_value(table, "max-function-sloc", 5, 1)?,
        max_inline_caller_sloc: min_int_value(table, "max-inline-caller-sloc", 50, 1)?,
        max_inline_caller_complexity: min_int_value(table, "max-inline-caller-complexity", 10, 1)?,
        max_inline_caller_cognitive_complexity: min_int_value(
            table,
            "max-inline-caller-cognitive-complexity",
            10,
            0,
        )?,
        max_inline_call_nesting: min_int_value(table, "max-inline-call-nesting", 3, 0)?,
    })
}

fn tool_excludes(document: &Value) -> Vec<String> {
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

fn read_config(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|_| format!("{}: failed to read config", path.display()))
}

fn parse_toml(path: &Path, raw: &str) -> Result<Value, String> {
    toml::from_str::<Value>(raw)
        .map_err(|error| format!("{}: failed to parse config: {error}", path.display()))
}

fn table_at<'a>(document: &'a Value, path: &[&str]) -> Option<&'a Map<String, Value>> {
    let mut current = document;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_table()
}

fn table_keys(table: Option<&Map<String, Value>>) -> Vec<String> {
    table
        .into_iter()
        .flat_map(|table| table.keys().cloned())
        .collect()
}

fn string_list_value(
    table: Option<&Map<String, Value>>,
    key: &str,
) -> Result<Option<Vec<String>>, String> {
    let Some(value) = table.and_then(|table| table.get(key)) else {
        return Ok(None);
    };
    let Some(array) = value.as_array() else {
        return Err(format!("{key} must be a list"));
    };
    array
        .iter()
        .map(|item| {
            item.as_str()
                .map(ToString::to_string)
                .ok_or_else(|| format!("{key} must be a list of strings"))
        })
        .collect::<Result<Vec<_>, _>>()
        .map(Some)
}

fn tool_string_list_value(table: &Map<String, Value>, key: &str) -> Option<Vec<String>> {
    let array = table.get(key)?.as_array()?;
    array
        .iter()
        .map(|item| item.as_str().map(ToString::to_string))
        .collect()
}

fn int_value(table: Option<&Map<String, Value>>, key: &str) -> Result<Option<usize>, String> {
    let Some(value) = table.and_then(|table| table.get(key)) else {
        return Ok(None);
    };
    let Some(value) = value.as_integer() else {
        return Err(format!("{key} must be an integer"));
    };
    usize::try_from(value)
        .map(Some)
        .map_err(|_| format!("{key} must be an integer"))
}

fn min_int_value(
    table: &Map<String, Value>,
    key: &str,
    default: usize,
    minimum: usize,
) -> Result<usize, String> {
    let value = int_value(Some(table), key)?.unwrap_or(default);
    if value < minimum {
        return Err(format!("{key} must be >= {minimum}"));
    }
    Ok(value)
}

fn bool_value(table: &Map<String, Value>, key: &str) -> Result<Option<bool>, String> {
    let Some(value) = table.get(key) else {
        return Ok(None);
    };
    value
        .as_bool()
        .map(Some)
        .ok_or_else(|| format!("{key} must be a boolean"))
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

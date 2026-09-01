//! Rust implementation of the `scb-check` command-line interface.

mod analyze;
mod args;
mod astgrep;
mod clones;
mod config;
mod directives;
mod languages;
mod model;
mod render;
mod rules;
mod walk;

use std::process::ExitCode;

use analyze::{AnalyzeError, analyze};
use args::{CheckOptions, Command, ParseArgsError, parse_args};
use astgrep::{AstGrepError, ast_grep_rule_document};
use config::{ConfigError, load_config};
use model::Report;
use render::{render_human, render_json};
use rules::structural_rule_document;
use thiserror::Error;
use walk::{WalkError, discover_sources};

#[derive(Debug, Error)]
enum CliError {
    #[error("{message}")]
    Usage { message: String },
    #[error("failed to determine current directory: {source}")]
    CurrentDirectory {
        #[source]
        source: std::io::Error,
    },
    #[error(transparent)]
    Config(#[from] ConfigError),
    #[error(transparent)]
    Walk(#[from] WalkError),
    #[error(transparent)]
    Analyze(#[from] AnalyzeError),
    #[error(transparent)]
    AstGrep(#[from] AstGrepError),
    #[error("no supported source files found at {}", path.display())]
    NoSourceFiles { path: std::path::PathBuf },
    #[error("no supported source files could be parsed at {}", path.display())]
    NoParsedFiles { path: std::path::PathBuf },
    #[error("rule not found: {rule_id}")]
    UnknownRule { rule_id: String },
}

/// Run the `scb-check` CLI with already split command-line arguments.
///
/// The iterator is consumed at the CLI boundary so argument parsing can own and normalize the
/// invocation before analysis begins; this avoids borrowing caller-managed argument storage.
pub fn run_cli<I>(raw_args: I) -> ExitCode
where
    I: IntoIterator<Item = String>,
{
    match run(raw_args) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
    }
}

fn run<I>(raw_args: I) -> Result<ExitCode, CliError>
where
    I: IntoIterator<Item = String>,
{
    let command = match parse_args(raw_args) {
        Ok(command) => command,
        Err(ParseArgsError::Help(message)) => {
            print!("{message}");
            return Ok(ExitCode::SUCCESS);
        }
        Err(ParseArgsError::Usage(message)) => return Err(CliError::Usage { message }),
    };
    match command {
        Command::Check(options) => run_check(&options),
        Command::Rule(rule_id) => run_rule(&rule_id),
        Command::Version => {
            println!("{}", env!("CARGO_PKG_VERSION"));
            Ok(ExitCode::SUCCESS)
        }
    }
}

fn run_check(options: &CheckOptions) -> Result<ExitCode, CliError> {
    let cwd = std::env::current_dir().map_err(|source| CliError::CurrentDirectory { source })?;
    let config = load_config(options.config_path.as_deref(), &cwd)?;
    log_debug(
        options.verbosity,
        format_args!(
            "config_loaded base_dir={} exclude_count={} context_lines={} low_use_short_function_enabled={}",
            config.base_dir.display(),
            config.exclude.len(),
            config.context_lines,
            config.low_use_short_function.enabled
        ),
    );
    let files = discover_sources(&options.path, &config, options.include_all)?;
    log_info(
        options.verbosity,
        format_args!(
            "files_discovered count={} path={}",
            files.len(),
            options.path.display()
        ),
    );
    for file in &files {
        log_debug(
            options.verbosity,
            format_args!(
                "source_file language={} path={}",
                file.language.as_str(),
                file.path.display()
            ),
        );
    }
    if files.is_empty() {
        return Err(CliError::NoSourceFiles {
            path: options.path.clone(),
        });
    }

    let report = analyze(
        &files,
        options.disable_sg,
        options.include_all,
        &config.low_use_short_function,
    )?;
    log_info(
        options.verbosity,
        format_args!(
            "analysis_complete files_scanned={} total_loc={} has_findings={}",
            report.files_scanned,
            report.total_loc,
            report.has_findings()
        ),
    );
    if report.files_scanned == 0 {
        return Err(CliError::NoParsedFiles {
            path: options.path.clone(),
        });
    }

    render_report(&report, options, config.context_lines);
    Ok(exit_code_for_report(&report))
}

fn log_info(verbosity: u8, message: std::fmt::Arguments<'_>) {
    if verbosity >= 1 {
        eprintln!("info {message}");
    }
}

fn log_debug(verbosity: u8, message: std::fmt::Arguments<'_>) {
    if verbosity >= 2 {
        eprintln!("debug {message}");
    }
}

fn render_report(report: &Report, options: &CheckOptions, context_lines: usize) {
    if options.output_json {
        println!("{}", render_json(report));
    } else {
        let rendered = render_human(report, options.min_duplicate_lines, context_lines);
        if !rendered.is_empty() {
            println!("{rendered}");
        }
    }
}

fn exit_code_for_report(report: &Report) -> ExitCode {
    if report.has_findings() {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}

fn run_rule(rule_id: &str) -> Result<ExitCode, CliError> {
    let Some(document) =
        ast_grep_rule_document(rule_id)?.or_else(|| structural_rule_document(rule_id))
    else {
        return Err(CliError::UnknownRule {
            rule_id: rule_id.to_string(),
        });
    };
    println!("{}", document.trim_end());
    Ok(ExitCode::SUCCESS)
}

#[cfg(test)]
mod test_support {
    use super::CliError;
    use std::ffi::OsStr;
    use std::fs;
    use std::ops::Deref;
    use std::path::{Path, PathBuf};

    use crate::analyze::analyze;
    use crate::config::load_config;
    use crate::model::Report;
    use crate::walk::discover_sources;

    #[derive(Debug)]
    pub struct TestDir {
        temp: assert_fs::TempDir,
    }

    impl Deref for TestDir {
        type Target = Path;

        fn deref(&self) -> &Self::Target {
            self.temp.path()
        }
    }

    impl AsRef<OsStr> for TestDir {
        fn as_ref(&self) -> &OsStr {
            self.temp.path().as_ref()
        }
    }

    impl AsRef<Path> for TestDir {
        fn as_ref(&self) -> &Path {
            self.temp.path()
        }
    }

    pub fn test_dir() -> TestDir {
        TestDir {
            temp: assert_fs::TempDir::new().expect("test dir should be created"),
        }
    }

    pub fn write(path: &Path, content: &str) {
        fs::write(path, content.trim_start()).expect("fixture should be writable");
    }

    pub fn workspace_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .expect("crate should live under the workspace root")
            .to_path_buf()
    }

    pub fn analyze_dir(
        root: &Path,
        disable_sg: bool,
        include_all: bool,
        config_path: Option<&Path>,
    ) -> Result<Report, CliError> {
        let config = load_config(config_path, root)?;
        let files = discover_sources(root, &config, include_all)?;
        Ok(analyze(
            &files,
            disable_sg,
            include_all,
            &config.low_use_short_function,
        )?)
    }
}

#[cfg(test)]
mod tests {
    use crate::run_rule;

    #[test]
    fn run_rule_accepts_ast_grep_and_structural_rules() {
        assert_eq!(
            run_rule("chained-dict-get").expect("ast-grep rule should resolve"),
            std::process::ExitCode::SUCCESS
        );
        assert_eq!(
            run_rule("trivial-wrapper").expect("structural rule should resolve"),
            std::process::ExitCode::SUCCESS
        );
    }

    #[test]
    fn run_rule_rejects_unknown_ids() {
        let error = run_rule("does-not-exist").expect_err("unknown rule should fail");

        assert_eq!(error.to_string(), "rule not found: does-not-exist");
    }
}

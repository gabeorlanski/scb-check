pub(crate) mod analyze;
pub(crate) mod args;
pub(crate) mod astgrep;
pub(crate) mod clones;
pub(crate) mod config;
pub(crate) mod directives;
pub(crate) mod model;
pub(crate) mod parser;
pub(crate) mod render;
pub(crate) mod rules;
pub(crate) mod walk;

use std::process::ExitCode;

use analyze::analyze;
use args::{CheckOptions, Command, parse_args};
use astgrep::ast_grep_rule_document;
use config::load_config;
use model::Report;
use render::{render_human, render_json};
use rules::structural_rule_document;
use walk::discover_sources;

fn main() -> ExitCode {
    match run() {
        Ok(code) => code,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<ExitCode, String> {
    let cli = parse_args(std::env::args().skip(1))?;
    match cli.command {
        Command::Check(options) => run_check(&options),
        Command::Rule(rule_id) => run_rule(&rule_id),
        Command::Version => {
            println!("{}", env!("CARGO_PKG_VERSION"));
            Ok(ExitCode::SUCCESS)
        }
    }
}

fn run_check(options: &CheckOptions) -> Result<ExitCode, String> {
    let cwd = std::env::current_dir().map_err(|error| error.to_string())?;
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
        return Err(format!(
            "no supported source files found at {}",
            options.path.display()
        ));
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
        return Err(format!(
            "no supported source files could be parsed at {}",
            options.path.display()
        ));
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

fn run_rule(rule_id: &str) -> Result<ExitCode, String> {
    let Some(document) =
        ast_grep_rule_document(rule_id)?.or_else(|| structural_rule_document(rule_id))
    else {
        return Err(format!("rule not found: {rule_id}"));
    };
    println!("{}", document.trim_end());
    Ok(ExitCode::SUCCESS)
}

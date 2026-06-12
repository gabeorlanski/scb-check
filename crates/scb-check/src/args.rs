use std::path::PathBuf;

use clap::{ArgAction, Parser, Subcommand, ValueEnum};

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CheckOptions {
    pub path: PathBuf,
    pub output_json: bool,
    pub include_all: bool,
    pub disable_sg: bool,
    pub min_duplicate_lines: Option<usize>,
    pub config_path: Option<PathBuf>,
    pub verbosity: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Command {
    Check(CheckOptions),
    Rule(String),
    Version,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Cli {
    pub command: Command,
}

#[derive(Debug, Parser)]
#[command(
    name = "scb-check",
    disable_help_flag = true,
    disable_version_flag = true
)]
struct RawCli {
    #[command(subcommand)]
    command: RawCommand,
}

#[derive(Debug, Subcommand)]
enum RawCommand {
    Check(RawCheckOptions),
    Rule { rule_id: String },
}

#[derive(Debug, Parser)]
struct RawCheckOptions {
    #[arg(long = "report")]
    report: bool,
    #[arg(long = "output-format")]
    output_format: Option<OutputFormat>,
    #[arg(long = "include-all")]
    include_all: bool,
    #[arg(long = "disable-sg")]
    disable_sg: bool,
    #[arg(long = "config")]
    config_path: Option<PathBuf>,
    #[arg(long = "min-duplicate-lines", value_parser = parse_min_duplicate_lines)]
    min_duplicate_lines: Option<usize>,
    #[arg(short = 'v', long = "verbosity", action = ArgAction::Count)]
    verbosity: u8,
    path: PathBuf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum OutputFormat {
    Human,
    Json,
}

pub(crate) fn parse_args<I>(raw_args: I) -> Result<Cli, String>
where
    I: IntoIterator<Item = String>,
{
    let args: Vec<String> = raw_args.into_iter().collect();
    if args.is_empty() {
        return Err("missing command".to_string());
    }
    if args == ["--version"] {
        return Ok(Cli {
            command: Command::Version,
        });
    }

    let mut clap_args = Vec::with_capacity(args.len() + 1);
    clap_args.push("scb-check".to_string());
    clap_args.extend(args);
    let output_json = output_json_from_args(&clap_args[1..]);
    let mut cli: Cli = RawCli::try_parse_from(clap_args)
        .map(Into::into)
        .map_err(|error| error.to_string())?;
    if let (Some(output_json), Command::Check(options)) = (output_json, &mut cli.command) {
        options.output_json = output_json;
    }
    Ok(cli)
}

impl From<RawCli> for Cli {
    fn from(raw: RawCli) -> Self {
        let command = match raw.command {
            RawCommand::Check(options) => Command::Check(options.into()),
            RawCommand::Rule { rule_id } => Command::Rule(rule_id),
        };
        Self { command }
    }
}

impl From<RawCheckOptions> for CheckOptions {
    fn from(raw: RawCheckOptions) -> Self {
        Self {
            path: raw.path,
            output_json: raw.report || raw.output_format == Some(OutputFormat::Json),
            include_all: raw.include_all,
            disable_sg: raw.disable_sg,
            min_duplicate_lines: raw.min_duplicate_lines,
            config_path: raw.config_path,
            verbosity: raw.verbosity,
        }
    }
}

fn parse_min_duplicate_lines(value: &str) -> Result<usize, String> {
    let parsed = value
        .parse::<usize>()
        .map_err(|_| format!("invalid --min-duplicate-lines: {value}"))?;
    if parsed == 0 {
        return Err("--min-duplicate-lines must be >= 1".to_string());
    }
    Ok(parsed)
}

fn output_json_from_args(args: &[String]) -> Option<bool> {
    let mut output_json = None;
    let mut index = 0;
    while index < args.len() {
        if let Some(value) = output_json_arg(args, index) {
            output_json = Some(value);
        }
        index += output_json_arg_width(args, index);
    }
    output_json
}

fn output_json_arg(args: &[String], index: usize) -> Option<bool> {
    let arg = args[index].as_str();
    if arg == "--report" {
        return Some(true);
    }
    if arg == "--output-format" {
        return args
            .get(index + 1)
            .and_then(|value| output_json_value(value));
    }
    arg.strip_prefix("--output-format=")
        .and_then(output_json_value)
}

fn output_json_arg_width(args: &[String], index: usize) -> usize {
    if args[index] == "--output-format" {
        2
    } else {
        1
    }
}

fn output_json_value(value: &str) -> Option<bool> {
    match value {
        "json" => Some(true),
        "human" => Some(false),
        _ => None,
    }
}

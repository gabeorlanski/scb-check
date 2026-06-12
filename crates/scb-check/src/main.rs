//! Binary entrypoint for the `scb-check` CLI.

use std::process::ExitCode;

fn main() -> ExitCode {
    scb_check::run_cli(std::env::args().skip(1))
}

//! Binary entrypoint for the `scb-check` CLI.

#![expect(
    clippy::multiple_crate_versions,
    reason = "Indirect ast-grep/toml dependencies currently resolve two winnow versions; no direct dependency pin fixes this without upstream churn."
)]

use std::process::ExitCode;

fn main() -> ExitCode {
    scb_check::run_cli(std::env::args().skip(1))
}

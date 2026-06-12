#![allow(
    dead_code,
    reason = "integration test crates use different helper subsets"
)]

use std::ffi::OsStr;
use std::fs;
use std::ops::Deref;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug)]
pub(crate) struct TestDir {
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

pub(crate) fn run_check(root: &Path) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_scb-check"))
        .args(["check", "--report", "--disable-sg"])
        .arg(root)
        .output()
        .expect("scb-check should run")
}

pub(crate) fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate should live under the workspace root")
        .to_path_buf()
}

pub(crate) fn write(path: &Path, content: &str) {
    fs::write(path, content.trim_start()).expect("fixture should be writable");
}

pub(crate) fn test_dir(_name: &str) -> TestDir {
    TestDir {
        temp: assert_fs::TempDir::new().expect("test dir should be created"),
    }
}

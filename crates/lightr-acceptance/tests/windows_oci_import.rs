//! Native Windows CLI proof for ADR-0021 OCI import preflight.

#![cfg(windows)]

#[path = "common/mod.rs"]
#[allow(dead_code)]
mod common;

use common::lightr_cmd;
use tempfile::TempDir;

const ERROR: &str = "lightr: unsupported: OCI layer import is unsupported on Windows (ADR-0021)";

fn assert_unsupported_without_home(home: &std::path::Path, args: &[&str]) {
    let output = lightr_cmd(home).args(args).output().expect("lightr spawns");
    assert_eq!(output.status.code(), Some(1), "{args:?} must exit 1");
    assert_eq!(String::from_utf8_lossy(&output.stderr).trim(), ERROR);
    assert!(
        !home.exists(),
        "{args:?} must reject before Store::open creates LIGHTR_HOME"
    );
}

#[test]
fn oci_import_routes_leave_missing_lightr_home_absent() {
    let tmp = TempDir::new().unwrap();
    let home = tmp.path().join("empty-lightr-home");
    let missing = tmp.path().join("missing.tar");
    let missing = missing.to_str().unwrap();

    assert_unsupported_without_home(&home, &["oci", "import", missing, "--name", "import"]);
    assert_unsupported_without_home(&home, &["oci", "load", "--input", missing]);
    assert_unsupported_without_home(
        &home,
        &["oci", "pull", "not a valid image ref", "--name", "pull"],
    );
}

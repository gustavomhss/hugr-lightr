//! `run -d` refuses a `LIGHTR_HOME` whose run `ctl.sock` would exceed the
//! host's AF_UNIX path limit, before it creates a run dir or a supervisor.
#![cfg(unix)]

use std::path::Path;
use std::process::{Command, Output};

/// `run -d` of a workload that would leave `marker` behind if it ever ran.
fn run_detached(home: &Path, marker: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_lightr"))
        .env("LIGHTR_HOME", home)
        .args(["run", "-d", "--dir"])
        .arg(home.parent().unwrap())
        .args(["--", "/usr/bin/touch"])
        .arg(marker)
        .output()
        .expect("run lightr")
}

fn run_entries(home: &Path) -> usize {
    std::fs::read_dir(home.join("run")).map_or(0, |dir| dir.count())
}

#[test]
fn run_detached_refuses_an_over_long_lightr_home_before_spawning() {
    let root = tempfile::tempdir().unwrap();
    // Any home this long puts `<home>/run/<id>/ctl.sock` past 107 bytes.
    let home = root.path().join("h".repeat(110));
    let marker = root.path().join("ran");

    let out = run_detached(&home, &marker);

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "stderr: {stderr}");
    assert!(out.stdout.is_empty(), "no run id may be printed");
    assert!(
        stderr.starts_with("lightr: invalid ref: detached run control socket path is "),
        "{stderr}"
    );
    assert!(stderr.contains("AF_UNIX limit"), "{stderr}");
    assert!(
        stderr.contains("set LIGHTR_HOME to a path at least"),
        "{stderr}"
    );
    assert_eq!(run_entries(&home), 0, "no run dir may be created");
    std::thread::sleep(std::time::Duration::from_millis(500));
    assert!(!marker.exists(), "no supervisor may run the workload");
}

#[test]
fn run_detached_with_a_short_lightr_home_still_starts() {
    // Positive control: the same command and layout succeed when the path fits.
    let root = tempfile::tempdir().unwrap();
    let home = root.path().join("h");
    let marker = root.path().join("ran");

    let out = run_detached(&home, &marker);

    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(run_entries(&home), 1);
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    while !marker.exists() && std::time::Instant::now() < deadline {
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    assert!(marker.exists(), "the detached workload must run");
}

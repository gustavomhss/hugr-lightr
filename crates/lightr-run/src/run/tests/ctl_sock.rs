//! `ctl.sock` path limit: the length check at its boundary, the refusal
//! message, the pre-spawn refusals (`create_run_prepared`, `respawn_run`) and
//! the supervisors' bind-failure handling (nothing started, terminal status).
#![cfg(unix)]

use crate::run::ctl::{
    bind_ctl_listener, check_sock_len, ctl_sock_path, ensure_ctl_sock_fits, CTL_SOCK_MAX_BYTES,
};
use crate::run::paths::{read_status_file, write_spec_json};
use crate::run::types::SpecOnDisk;
use lightr_core::LightrError;
use std::path::{Path, PathBuf};

/// A path of exactly `len` bytes made of `unit` repeated, behind a leading `/`.
fn path_of_bytes(len: usize, unit: &str) -> PathBuf {
    let body = unit.repeat((len - 1) / unit.len());
    let pad = "a".repeat(len - 1 - body.len());
    let path = PathBuf::from(format!("/{body}{pad}"));
    assert_eq!(path.as_os_str().len(), len, "fixture length");
    path
}

/// A real directory whose `ctl.sock` is past the host limit.
fn long_dir(root: &Path) -> PathBuf {
    let dir = root.join("d".repeat(CTL_SOCK_MAX_BYTES));
    std::fs::create_dir_all(&dir).unwrap();
    assert!(ctl_sock_path(&dir).as_os_str().len() > CTL_SOCK_MAX_BYTES);
    dir
}

#[test]
fn max_bytes_is_sun_path_minus_the_nul() {
    // Independent oracle: the documented sizes of `sockaddr_un.sun_path`.
    #[cfg(target_os = "macos")]
    assert_eq!(CTL_SOCK_MAX_BYTES, 103);
    #[cfg(target_os = "linux")]
    assert_eq!(CTL_SOCK_MAX_BYTES, 107);
}

#[test]
fn length_check_boundary() {
    let max = CTL_SOCK_MAX_BYTES;
    assert!(check_sock_len(&path_of_bytes(max - 1, "a"), max).is_ok());
    assert!(check_sock_len(&path_of_bytes(max, "a"), max).is_ok());
    assert!(check_sock_len(&path_of_bytes(max + 1, "a"), max).is_err());
}

#[test]
fn length_check_counts_bytes_not_chars() {
    let max = CTL_SOCK_MAX_BYTES;
    // `é` is 2 bytes: max bytes fits, max + 1 bytes does not.
    assert!(check_sock_len(&path_of_bytes(max, "é"), max).is_ok());
    let over = path_of_bytes(max + 1, "é");
    assert!(over.to_str().unwrap().chars().count() <= max);
    assert!(check_sock_len(&over, max).is_err());
}

#[test]
fn refusal_names_length_limit_path_and_remedy() {
    let max = CTL_SOCK_MAX_BYTES;
    let sock = path_of_bytes(max + 5, "a");
    let msg = check_sock_len(&sock, max).unwrap_err();
    assert_eq!(
        msg,
        format!(
            "detached run control socket path is {} bytes, over this host's {max}-byte \
             AF_UNIX limit: {}; set LIGHTR_HOME to a path at least 5 bytes shorter",
            max + 5,
            sock.display()
        )
    );
}

#[test]
fn ensure_refuses_long_run_dir_as_exit_2_class() {
    let root = tempfile::tempdir().unwrap();
    assert!(ensure_ctl_sock_fits(root.path()).is_ok());
    // InvalidRef maps to exit 2 at the CLI (exit::error_exit_code).
    let err = ensure_ctl_sock_fits(&long_dir(root.path())).unwrap_err();
    assert!(matches!(err, LightrError::InvalidRef(_)), "{err:?}");
}

#[test]
fn bind_failure_is_recorded_and_leaves_no_socket() {
    let root = tempfile::tempdir().unwrap();
    let dir = long_dir(root.path());
    assert!(bind_ctl_listener(&dir).is_err());
    assert_eq!(read_status_file(&dir).as_deref(), Some("exited 2"));
    let log = std::fs::read_to_string(dir.join("stderr.log")).unwrap();
    assert!(log.contains("AF_UNIX limit"), "{log}");
    assert!(!ctl_sock_path(&dir).exists());
}

#[test]
fn bound_listener_removes_its_socket_on_drop() {
    let root = tempfile::tempdir().unwrap();
    let ctl = bind_ctl_listener(root.path()).unwrap();
    assert!(ctl_sock_path(root.path()).exists());
    drop(ctl);
    assert!(!ctl_sock_path(root.path()).exists());
    assert_eq!(read_status_file(root.path()), None);
}

#[test]
fn create_run_prepared_refuses_before_the_run_dir_exists() {
    let _guard = crate::run::tests::ENV_LOCK
        .lock()
        .unwrap_or_else(|p| p.into_inner());
    let root = tempfile::tempdir().unwrap();
    let home = long_dir(root.path());
    std::env::set_var("LIGHTR_HOME", &home);
    let store = lightr_store::Store::open(root.path().join("store")).unwrap();
    let spec = crate::RunSpec {
        cwd: root.path().to_path_buf(),
        command: vec!["/bin/true".to_string()],
        ..Default::default()
    };
    let result = crate::run::spawn::create_run_prepared(
        &spec,
        &store,
        None,
        lightr_engine::EngineKind::Native,
        None,
        &[],
    );
    std::env::remove_var("LIGHTR_HOME");
    assert!(matches!(result, Err(LightrError::InvalidRef(_))));
    assert!(!home.join("run").exists(), "no run dir may be created");
}

#[test]
fn respawn_refuses_before_touching_the_run() {
    let root = tempfile::tempdir().unwrap();
    let home = long_dir(root.path());
    let dir = home.join("run").join("id-long");
    std::fs::create_dir_all(&dir).unwrap();
    write_spec_json(&dir, &SpecOnDisk::default()).unwrap();
    std::fs::write(dir.join("status"), "exited 0").unwrap();
    let err = crate::run::lifecycle::respawn_run(&home, "id-long").unwrap_err();
    assert!(matches!(err, LightrError::InvalidRef(_)), "{err:?}");
    assert_eq!(read_status_file(&dir).as_deref(), Some("exited 0"));
}

/// A spec whose workload would leave `marker` behind if it ever ran.
fn marker_spec(cwd: &Path, marker: &Path, engine: &str) -> SpecOnDisk {
    SpecOnDisk {
        cwd: cwd.to_string_lossy().into_owned(),
        command: vec!["/usr/bin/touch".to_string(), marker.display().to_string()],
        engine: engine.to_string(),
        rootfs_ref: (engine == "vz").then(|| "never-hydrated".to_string()),
        ..Default::default()
    }
}

#[test]
fn native_supervisor_starts_nothing_without_a_control_socket() {
    let root = tempfile::tempdir().unwrap();
    let dir = long_dir(root.path());
    let marker = root.path().join("ran");
    let spec = marker_spec(root.path(), &marker, "native");
    let store = lightr_store::Store::open(root.path().join("store")).unwrap();
    assert!(crate::run::supervise_native::supervise_native(&dir, &spec, &store).is_err());
    std::thread::sleep(std::time::Duration::from_millis(200));
    assert!(!marker.exists(), "the workload must not run");
    assert!(!dir.join("pid").exists());
    assert_eq!(read_status_file(&dir).as_deref(), Some("exited 2"));
}

#[test]
fn vz_supervisor_hydrates_and_boots_nothing_without_a_control_socket() {
    let root = tempfile::tempdir().unwrap();
    let dir = long_dir(root.path());
    let spec = marker_spec(root.path(), &root.path().join("ran"), "vz");
    let store = lightr_store::Store::open(root.path().join("store")).unwrap();
    let err = crate::run::svz::supervise_vz(&dir, &spec, &store).unwrap_err();
    // The rootfs ref does not exist, so reaching hydration would fail with a
    // different error and create `rootfs/`. Neither may happen.
    assert!(err.to_string().contains("AF_UNIX limit"), "{err}");
    assert!(!dir.join("rootfs").exists());
    assert!(!dir.join("pid").exists());
    assert_eq!(read_status_file(&dir).as_deref(), Some("exited 2"));
}

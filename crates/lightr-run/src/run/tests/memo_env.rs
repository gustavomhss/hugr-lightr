//! Real native children and the 0.1.1 explicit-env cache compatibility boundary.
#![cfg(unix)]

use crate::run::ac::encode_ac_record;
use crate::run::memo::{assemble_key, build_key, run_memoized};
use crate::run::types::RunSpec;
use lightr_core::Digest;
use lightr_index::{scan, Index};
use lightr_store::Store;
use std::fs;

fn fixture() -> (tempfile::TempDir, std::sync::MutexGuard<'static, ()>) {
    let guard = super::ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
    let home = tempfile::tempdir().unwrap();
    std::env::set_var("LIGHTR_HOME", home.path());
    fs::create_dir(home.path().join("work")).unwrap();
    (home, guard)
}

fn spec(home: &std::path::Path) -> RunSpec {
    RunSpec {
        cwd: home.join("work"),
        command: vec![
            "/bin/sh".into(),
            "-c".into(),
            "printf '%s' \"$PATH\"; printf x >> \"$1\"".into(),
            "--".into(),
            home.join("counter").to_string_lossy().into_owned(),
        ],
        env_explicit: vec![("PATH".into(), "/lightr/explicit v1=ok".into())],
        ..Default::default()
    }
}

// Independent 0.1.1 encoder for these cwd-only, no-env_keys/no-mount fixtures.
fn legacy_key(spec: &RunSpec) -> Digest {
    let mut h = blake3::Hasher::new();
    h.update(b"lightr/run/v1\0");
    let mut index = Index::load_for(&spec.cwd.canonicalize().unwrap()).unwrap();
    let report = scan(&spec.cwd, &mut index).unwrap();
    h.update(spec.cwd.as_os_str().as_encoded_bytes());
    h.update(b"\0");
    h.update(&report.manifest.digest().0);
    for arg in &spec.command {
        h.update(&(arg.len() as u64).to_le_bytes());
        h.update(arg.as_bytes());
    }
    if !spec.env_explicit.is_empty() {
        h.update(b"\x03env_explicit\0");
        let mut pairs = spec.env_explicit.clone();
        pairs.sort();
        for (key, value) in pairs {
            h.update(key.as_bytes());
            h.update(b"=");
            h.update(value.as_bytes());
            h.update(b"\0");
        }
    }
    h.update(format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH).as_bytes());
    Digest(*h.finalize().as_bytes())
}

#[test]
fn explicit_env_reaches_child_and_memoizes() {
    let (home, _guard) = fixture();
    let store = Store::open(home.path().join("store")).unwrap();
    let mut spec = spec(home.path());
    let first = run_memoized(&spec, &store).unwrap();
    assert_eq!(first.exit_code, 0);
    assert!(!first.hit);
    assert_eq!(first.stdout, b"/lightr/explicit v1=ok");
    let second = run_memoized(&spec, &store).unwrap();
    assert!(second.hit);
    assert_eq!(second.key, first.key);
    assert_eq!(second.stdout, first.stdout);
    assert_eq!(fs::read(home.path().join("counter")).unwrap(), b"x");
    spec.env_explicit[0].1 = "/lightr/explicit v2=ok".into();
    let changed = run_memoized(&spec, &store).unwrap();
    assert!(!changed.hit);
    assert_ne!(changed.key, first.key);
    assert_eq!(changed.stdout, b"/lightr/explicit v2=ok");
    assert_eq!(fs::read(home.path().join("counter")).unwrap(), b"xx");
    assert_eq!(
        build_key(&spec).unwrap(),
        assemble_key(&spec, &store, false).unwrap()
    );
}

#[test]
fn explicit_env_overrides_generated_env_and_preserves_parent() {
    let (home, _guard) = fixture();
    let store = Store::open(home.path().join("store")).unwrap();
    let mut spec = RunSpec {
        cwd: home.path().join("work"),
        command: vec![
            "/bin/sh".into(),
            "-c".into(),
            "printf '%s|%s' \"$HOSTNAME\" \"$LIGHTR_HOME\"".into(),
        ],
        hostname: Some("generated-host".into()),
        env_explicit: vec![("HOSTNAME".into(), "explicit-host".into())],
        ..Default::default()
    };
    let explicit = run_memoized(&spec, &store).unwrap();
    assert!(!explicit.hit);
    assert_eq!(explicit.exit_code, 0);
    assert_eq!(
        explicit.stdout,
        format!("explicit-host|{}", home.path().display()).as_bytes()
    );
    spec.env_explicit.clear();
    spec.hostname = None;
    spec.command[2] = "printf '%s' \"$LIGHTR_HOME\"".into();
    let inherited = run_memoized(&spec, &store).unwrap();
    assert!(
        !inherited.hit,
        "empty-env passthrough must execute, not replay"
    );
    assert_eq!(inherited.exit_code, 0);
    assert_eq!(inherited.stdout, home.path().as_os_str().as_encoded_bytes());
}

#[test]
fn legacy_explicit_env_cache_is_not_replayed() {
    let (home, _guard) = fixture();
    let store = Store::open(home.path().join("store")).unwrap();
    let mut spec = spec(home.path());
    // Reproduce 0.1.1 execution: inherit parent env, ignore explicit overrides.
    let old = std::process::Command::new(&spec.command[0])
        .args(&spec.command[1..])
        .current_dir(&spec.cwd)
        .output()
        .unwrap();
    assert!(old.status.success());
    assert_ne!(old.stdout, b"/lightr/explicit v1=ok");
    let record = encode_ac_record(
        0,
        &store.put_bytes(&old.stdout).unwrap(),
        &store.put_bytes(&old.stderr).unwrap(),
    );
    let legacy = legacy_key(&spec);
    store.ac_put(&legacy, &record).unwrap();
    let corrected = run_memoized(&spec, &store).unwrap();
    assert!(
        !corrected.hit,
        "0.1.1 result must not bypass corrected spawn"
    );
    assert_ne!(corrected.key, legacy);
    assert_eq!(corrected.stdout, b"/lightr/explicit v1=ok");
    assert_eq!(store.ac_get(&legacy).unwrap().unwrap(), record);
    assert!(run_memoized(&spec, &store).unwrap().hit);
    assert_eq!(fs::read(home.path().join("counter")).unwrap(), b"xx");

    // Empty explicit env keeps its 0.1.1 key and can replay its valid old record.
    spec.env_explicit.clear();
    let unchanged = legacy_key(&spec);
    assert_eq!(build_key(&spec).unwrap(), unchanged);
    store.ac_put(&unchanged, &record).unwrap();
    let replay = run_memoized(&spec, &store).unwrap();
    assert!(replay.hit);
    assert_eq!(replay.stdout, old.stdout);
    assert_eq!(fs::read(home.path().join("counter")).unwrap(), b"xx");
}

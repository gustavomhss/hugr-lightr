use super::*;

const PASSWD: &str = "root:x:0:0:root:/root:/bin/sh\ndock:x:1000:1000::/home/dock:/bin/sh\n";

fn s(v: &[&str]) -> Vec<String> {
    v.iter().map(|x| x.to_string()).collect()
}

fn pairs(v: &[(&str, &str)]) -> Vec<(String, String)> {
    v.iter()
        .map(|(k, x)| (k.to_string(), x.to_string()))
        .collect()
}

/// The env lock plus the temp home it points `LIGHTR_HOME` at: other tests
/// swap `LIGHTR_HOME`, which the snapshot path reads.
type Fixture = (std::sync::MutexGuard<'static, ()>, tempfile::TempDir);

/// A store holding `name` = a tree with `files` (path, bytes).
fn store_with(name: &str, files: &[(&str, &[u8])]) -> (Fixture, Store) {
    let guard = crate::test_lock::ENV_LOCK
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    std::env::set_var("LIGHTR_HOME", tmp.path());
    let store = Store::open(tmp.path().join("store")).unwrap();
    let tree = tmp.path().join("tree");
    std::fs::create_dir_all(tree.join("etc")).unwrap();
    for (path, bytes) in files {
        std::fs::write(tree.join(path), bytes).unwrap();
    }
    lightr_index::snapshot(&tree, &store, name).unwrap();
    ((guard, tmp), store)
}

#[test]
fn oci_config_supplies_entrypoint_env_user_and_workdir() {
    let (_tmp, store) = store_with("img", &[("etc/passwd", PASSWD.as_bytes())]);
    let oci = br#"{"config":{"Entrypoint":["/init.sh"],"Cmd":["serve"],
        "Env":["PATH=/opt/bin:/usr/bin","LANG=C"],"WorkingDir":"/srv","User":"dock"}}"#;
    store.image_config_put("img", oci).unwrap();
    let run = resolve_vz_guest(&store, "img", &[], None, &[], None, None).unwrap();
    assert_eq!(
        run,
        VzGuestRun {
            argv: s(&["/init.sh", "serve"]),
            env: pairs(&[("PATH", "/opt/bin:/usr/bin"), ("LANG", "C")]),
            user: Some("dock".to_string()),
            workdir: Some("/srv".to_string()),
        }
    );
}

#[test]
fn cli_flags_override_the_image_config() {
    let (_tmp, store) = store_with("img", &[("etc/passwd", PASSWD.as_bytes())]);
    store
        .image_config_put(
            "img",
            br#"{"config":{"Entrypoint":["/init.sh"],"Cmd":["serve"],"Env":["LANG=C","A=1"],"User":"dock","WorkingDir":"/srv"}}"#,
        )
        .unwrap();
    let ep = s(&["/bin/sh"]);
    let run = resolve_vz_guest(
        &store,
        "img",
        &s(&["-c", "id"]),
        Some(&ep),
        &pairs(&[("LANG", "C.UTF-8"), ("B", "2")]),
        Some("0:0"),
        Some("/tmp"),
    )
    .unwrap();
    assert_eq!(
        run.argv,
        s(&["/bin/sh", "-c", "id"]),
        "--entrypoint drops CMD"
    );
    assert_eq!(
        run.env,
        pairs(&[("LANG", "C.UTF-8"), ("A", "1"), ("B", "2")]),
        "image ENV < -e"
    );
    assert_eq!(run.user.as_deref(), Some("0:0"));
    assert_eq!(run.workdir.as_deref(), Some("/tmp"));
    let run = resolve_vz_guest(&store, "img", &s(&["true"]), None, &[], None, None).unwrap();
    assert_eq!(
        run.argv,
        s(&["/init.sh", "true"]),
        "CLI command replaces CMD"
    );
}

#[test]
fn lightr_build_sidecar_wins_and_must_parse() {
    let sidecar = br#"{"cmd":["echo","from-sidecar"],"env":[["K","V"]]}"#;
    let (_tmp, store) = store_with("img", &[(".lightr-image.json", sidecar)]);
    store
        .image_config_put("img", br#"{"config":{"Cmd":["oci"]}}"#)
        .unwrap();
    let run = resolve_vz_guest(&store, "img", &[], None, &[], None, None).unwrap();
    assert_eq!(run.argv, s(&["echo", "from-sidecar"]));
    assert_eq!(run.env, pairs(&[("K", "V")]));
}

#[test]
fn malformed_sidecar_fails_closed() {
    let (_tmp, store) = store_with("bad", &[(".lightr-image.json", b"{nope")]);
    assert!(resolve_vz_guest(&store, "bad", &s(&["true"]), None, &[], None, None).is_err());
}

#[test]
fn unresolvable_user_fails_before_boot() {
    let (_tmp, store) = store_with("img", &[("etc/passwd", PASSWD.as_bytes())]);
    assert!(resolve_vz_guest(&store, "img", &s(&["id"]), None, &[], Some("ghost"), None).is_err());
    assert!(resolve_vz_guest(&store, "img", &s(&["id"]), None, &[], Some("dock"), None).is_ok());
    assert!(resolve_vz_guest(&store, "img", &s(&["id"]), None, &[], Some("4242"), None).is_ok());
    // An image USER is checked too (not only -u).
    store
        .image_config_put("img", br#"{"config":{"User":"ghost"}}"#)
        .unwrap();
    assert!(resolve_vz_guest(&store, "img", &s(&["id"]), None, &[], None, None).is_err());
}

#[test]
fn missing_ref_is_an_error() {
    let (_tmp, store) = store_with("img", &[]);
    assert!(resolve_vz_guest(&store, "nope", &s(&["id"]), None, &[], None, None).is_err());
}

use super::*;
use crate::engine::spec::ResolvedMount;

const PASSWD: &str = "root:x:0:0:root:/root:/bin/sh\n\
                      # comment\n\
                      dock:x:1000:1000:Dock:/home/dock:/bin/bash\n\
                      broken-line\n\
                      nohome:x:1001:1001::\n";
const GROUP: &str = "root:x:0:\n\
                     video:x:44:dock\n\
                     audio:x:29:other,dock\n\
                     dock:x:1000:\n\
                     staff:x:50:\n";

fn spec<'a>(
    command: &'a [String],
    env: &'a [(String, String)],
    mounts: &'a [ResolvedMount],
) -> ExecSpec<'a> {
    ExecSpec {
        cwd: Path::new("/host/cwd"),
        command,
        rootfs: None,
        limits: lightr_core::ResourceLimits::default(),
        net: false,
        net_isolate: false,
        net_fd: None,
        net_mac: None,
        mounts,
        env,
        workdir: None,
        user: None,
        hostname: None,
        add_host: &[],
        dns: &[],
        mesh_ip: None,
        read_only: false,
        shm_size: None,
        cap_drop: &[],
        cap_add: &[],
        init: false,
        join_netns: None,
        cgroup_name: None,
        exec_ready_fd: None,
        apparmor: None,
        seccomp: None,
        bind_mounts: &[],
        resolv_conf: None,
        tmpfs: &[],
        ulimits: &[],
        oom_score_adj: None,
    }
}

fn pairs(list: &[(&str, &str)]) -> Vec<(String, String)> {
    list.iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

fn rootfs_with_db() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::create_dir(dir.path().join("etc")).unwrap();
    std::fs::write(dir.path().join("etc/passwd"), PASSWD).unwrap();
    std::fs::write(dir.path().join("etc/group"), GROUP).unwrap();
    dir
}

// ── env precedence ─────────────────────────────────────────────────────

#[test]
fn guest_env_starts_with_guest_path_and_later_keys_win_in_place() {
    let env = guest_env(&pairs(&[
        ("LANG", "C"),
        ("PATH", "/opt/bin:/usr/bin"),
        ("LANG", "C.UTF-8"),
    ]));
    assert_eq!(
        env,
        pairs(&[("PATH", "/opt/bin:/usr/bin"), ("LANG", "C.UTF-8")]),
        "image ENV then -e: later wins, first position kept"
    );
    assert_eq!(guest_env(&[]), pairs(&[("PATH", GUEST_PATH)]));
}

#[test]
fn home_defaults_from_passwd_and_explicit_home_wins() {
    let rootfs = rootfs_with_db();
    let cmd = ["id".to_string()];
    let (init, _) = build_init_spec(&spec(&cmd, &[], &[]), rootfs.path()).unwrap();
    assert!(init
        .env
        .contains(&("HOME".to_string(), "/root".to_string())));
    let mut s = spec(&cmd, &[], &[]);
    s.user = Some("dock");
    let (init, _) = build_init_spec(&s, rootfs.path()).unwrap();
    assert!(init
        .env
        .contains(&("HOME".to_string(), "/home/dock".to_string())));
    let env = pairs(&[("HOME", "/x")]);
    let (init, _) = build_init_spec(&spec(&cmd, &env, &[]), rootfs.path()).unwrap();
    assert_eq!(init.env.iter().filter(|(k, _)| k == "HOME").count(), 1);
    assert!(init.env.contains(&("HOME".to_string(), "/x".to_string())));
}

// ── user resolution ────────────────────────────────────────────────────

fn resolve(spec: &str) -> Result<ResolvedUser> {
    resolve_guest_user(spec, Some(PASSWD), Some(GROUP))
}

#[test]
fn user_name_resolves_with_primary_and_supplementary_groups() {
    let r = resolve("dock").unwrap();
    assert_eq!(
        r.user,
        GuestUser {
            uid: 1000,
            gid: 1000,
            groups: vec![1000, 44, 29],
        }
    );
    assert_eq!(r.home, "/home/dock");
}

#[test]
fn explicit_group_drops_supplementary_groups() {
    assert_eq!(resolve("dock:staff").unwrap().user.groups, vec![50]);
    assert_eq!(resolve("dock:7").unwrap().user.gid, 7);
}

#[test]
fn numeric_user_need_not_exist_in_the_image() {
    let r = resolve("4242").unwrap();
    assert_eq!(
        (r.user.uid, r.user.gid, r.user.groups, r.home.as_str()),
        (4242, 0, vec![0], "/")
    );
    let r = resolve("1000:1000").unwrap();
    assert_eq!((r.user.uid, r.user.gid), (1000, 1000));
    assert_eq!(resolve("1001").unwrap().home, "/", "empty home → /");
}

#[test]
fn unresolvable_or_malformed_users_fail() {
    for bad in ["ghost", "dock:nogroup", "", ":1", "dock:"] {
        assert!(resolve(bad).is_err(), "{bad:?} must fail before boot");
    }
    assert!(
        resolve_guest_user("dock", None, None).is_err(),
        "no passwd ⇒ names cannot resolve"
    );
}

#[test]
fn image_db_symlink_is_refused() {
    let rootfs = tempfile::tempdir().unwrap();
    std::fs::create_dir(rootfs.path().join("etc")).unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("/etc/passwd", rootfs.path().join("etc/passwd")).unwrap();
    #[cfg(unix)]
    assert!(read_image_db(rootfs.path(), "passwd").is_err());
    assert_eq!(read_image_db(rootfs.path(), "group").unwrap(), None);
}

// ── workdir, volumes, ABI ──────────────────────────────────────────────

#[test]
fn workdir_must_be_absolute_and_defaults_to_root() {
    let rootfs = rootfs_with_db();
    let cmd = ["pwd".to_string()];
    let (init, _) = build_init_spec(&spec(&cmd, &[], &[]), rootfs.path()).unwrap();
    assert_eq!(init.cwd, "/");
    let mut s = spec(&cmd, &[], &[]);
    s.workdir = Some("/srv/app");
    assert_eq!(
        build_init_spec(&s, rootfs.path()).unwrap().0.cwd,
        "/srv/app"
    );
    s.workdir = Some("relative");
    assert!(build_init_spec(&s, rootfs.path()).is_err());
}

fn bind(source: &str, target: &str, readonly: bool) -> ResolvedMount {
    ResolvedMount {
        kind: MountKind::HostBind,
        source: Some(source.to_string()),
        target: target.to_string(),
        readonly,
    }
}

#[test]
fn host_dir_binds_become_tagged_shares_and_guest_volumes() {
    let rootfs = rootfs_with_db();
    let a = tempfile::tempdir().unwrap();
    let b = tempfile::tempdir().unwrap();
    let mounts = [
        bind(a.path().to_str().unwrap(), "/data", true),
        bind(b.path().to_str().unwrap(), "/work", false),
    ];
    let cmd = ["true".to_string()];
    let (init, shares) = build_init_spec(&spec(&cmd, &[], &mounts), rootfs.path()).unwrap();
    assert_eq!(
        shares,
        vec![
            VzVolumeShare {
                host: std::fs::canonicalize(a.path()).unwrap(),
                tag: "vol0".to_string(),
                readonly: true,
            },
            VzVolumeShare {
                host: std::fs::canonicalize(b.path()).unwrap(),
                tag: "vol1".to_string(),
                readonly: false,
            },
        ]
    );
    assert_eq!(
        init.volumes,
        vec![
            GuestVolume {
                tag: "vol0".to_string(),
                target: "/data".to_string(),
                readonly: true,
            },
            GuestVolume {
                tag: "vol1".to_string(),
                target: "/work".to_string(),
                readonly: false,
            },
        ]
    );
}

#[test]
fn bad_volumes_fail_before_boot() {
    let rootfs = rootfs_with_db();
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("f");
    std::fs::write(&file, b"x").unwrap();
    let d = dir.path().to_str().unwrap();
    let cases = [
        bind(file.to_str().unwrap(), "/f", false),
        bind("/definitely/not/here", "/x", false),
        bind(d, "relative", false),
        bind(d, "/", false),
        bind(d, "/a/../b", false),
        ResolvedMount {
            kind: MountKind::NamedVolume,
            source: Some("cache".to_string()),
            target: "/cache".to_string(),
            readonly: false,
        },
    ];
    let cmd = ["true".to_string()];
    for m in cases {
        let target = m.target.clone();
        let mounts = [m];
        assert!(
            build_init_spec(&spec(&cmd, &[], &mounts), rootfs.path()).is_err(),
            "{target} must be refused"
        );
    }
}

#[test]
fn abi1_specs_need_abi1_and_new_fields_need_abi2() {
    let rootfs = rootfs_with_db();
    let cmd = ["true".to_string()];
    let env = pairs(&[("A", "1")]);
    let mut s = spec(&cmd, &env, &[]);
    s.workdir = Some("/srv");
    let (init, _) = build_init_spec(&s, rootfs.path()).unwrap();
    assert_eq!(required_init_abi(&init), 1, "ABI 1 applied env + cwd");
    s.user = Some("dock");
    let (init, _) = build_init_spec(&s, rootfs.path()).unwrap();
    assert_eq!(required_init_abi(&init), 2);
    s.user = None;
    s.shm_size = Some(1 << 20);
    let (init, _) = build_init_spec(&s, rootfs.path()).unwrap();
    assert_eq!(required_init_abi(&init), 2);
    let dir = tempfile::tempdir().unwrap();
    let mounts = [bind(dir.path().to_str().unwrap(), "/d", false)];
    let (init, _) = build_init_spec(&spec(&cmd, &[], &mounts), rootfs.path()).unwrap();
    assert_eq!(required_init_abi(&init), 2);
}

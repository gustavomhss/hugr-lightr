use super::*;
use std::io;

fn sample_spec() -> InitSpec {
    InitSpec {
        command: vec!["/bin/echo".to_string(), "hi".to_string()],
        cwd: "/work".to_string(),
        env: vec![
            ("PATH".to_string(), "/usr/bin".to_string()),
            ("LANG".to_string(), "C".to_string()),
        ],
        net: false,
        suspend_gate: false,
        user: None,
        volumes: Vec::new(),
        shm_size: None,
    }
}

// ── InitSpec json roundtrip ────────────────────────────────────────────

#[test]
fn initspec_json_roundtrip_is_stable() {
    let spec = sample_spec();
    let bytes = spec.to_json();
    let back = InitSpec::from_json(&bytes).expect("roundtrip parses");
    assert_eq!(spec, back, "roundtrip must preserve the spec");
    assert_eq!(bytes, back.to_json(), "serialization is stable");
}

#[test]
fn initspec_from_json_rejects_garbage() {
    let err = InitSpec::from_json(b"{ not json").unwrap_err();
    assert!(!err.is_empty(), "parse error must carry a message");
}

#[test]
fn initspec_from_json_without_net_defaults_to_false() {
    // Old host JSON predates the `net` field; serde(default) ⇒ net == false,
    // so the non-networked path stays byte-identical for back-compat.
    let spec = InitSpec::from_json(b"{\"command\":[],\"cwd\":\"/\",\"env\":[]}")
        .expect("legacy json parses");
    assert!(!spec.net, "missing net defaults to false");
}

// ── FakeOps / VecSink seams ────────────────────────────────────────────

/// A captured `spawn_wait` call: (command, cwd, env, user).
type SpawnCall = (
    Vec<String>,
    String,
    Vec<(String, String)>,
    Option<GuestUser>,
);

fn sample_gate() -> SuspendGate {
    SuspendGate {
        version: 1,
        instance_id: "vz-1".to_string(),
        release_token: "token-1".to_string(),
    }
}

/// Records the lifecycle steps in order and returns configurable outcomes.
struct FakeOps {
    steps: Vec<&'static str>,
    spec: InitSpec,
    spawn_result: io::Result<i32>,
    spawned: Option<SpawnCall>,
    published: bool,
    released: bool,
    /// The `pid_proof` gate `spawn_wait` was asked to prove (`None` = no proof).
    pid_proof: Option<Option<SuspendGate>>,
    fail_at: Option<&'static str>, // "mount" | "read" | "enter" | "setup"
    /// The spec `setup_guest` was handed (proves it sees user/volumes/shm).
    setup_spec: Option<InitSpec>,
}

impl FakeOps {
    fn spawning(code: i32) -> Self {
        FakeOps {
            steps: Vec::new(),
            spec: sample_spec(),
            spawn_result: Ok(code),
            spawned: None,
            published: false,
            released: false,
            pid_proof: None,
            fail_at: None,
            setup_spec: None,
        }
    }

    fn spawn_failing() -> Self {
        FakeOps {
            steps: Vec::new(),
            spec: sample_spec(),
            spawn_result: Err(io::Error::from_raw_os_error(2)), // ENOENT
            spawned: None,
            published: false,
            released: false,
            pid_proof: None,
            fail_at: None,
            setup_spec: None,
        }
    }

    fn failing_at(step: &'static str) -> Self {
        FakeOps {
            steps: Vec::new(),
            spec: sample_spec(),
            spawn_result: Ok(0),
            spawned: None,
            published: false,
            released: false,
            pid_proof: None,
            fail_at: Some(step),
            setup_spec: None,
        }
    }

    fn maybe_fail(&mut self, step: &'static str) -> io::Result<()> {
        self.steps.push(step);
        if self.fail_at == Some(step) {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!("{step} denied"),
            ));
        }
        Ok(())
    }
}

impl GuestOps for FakeOps {
    fn mount_rootfs(&mut self) -> io::Result<()> {
        self.maybe_fail("mount")
    }

    fn read_spec(&mut self) -> io::Result<InitSpec> {
        self.maybe_fail("read")?;
        Ok(self.spec.clone())
    }

    fn enter_rootfs(&mut self) -> io::Result<()> {
        self.maybe_fail("enter")
    }

    fn setup_guest(&mut self, spec: &InitSpec) -> io::Result<()> {
        self.setup_spec = Some(spec.clone());
        self.maybe_fail("setup")
    }

    fn spawn_wait(
        &mut self,
        cmd: &[String],
        cwd: &str,
        env: &[(String, String)],
        user: Option<&GuestUser>,
        pid_proof: Option<&SuspendGate>,
    ) -> io::Result<i32> {
        self.steps.push("spawn");
        self.pid_proof = Some(pid_proof.cloned());
        self.spawned = Some((cmd.to_vec(), cwd.to_string(), env.to_vec(), user.cloned()));
        match &self.spawn_result {
            Ok(code) => Ok(*code),
            Err(e) => Err(io::Error::from(e.kind())),
        }
    }

    fn publish_ip(&mut self) -> io::Result<()> {
        self.steps.push("publish_ip");
        self.published = true;
        Ok(())
    }

    fn await_suspend_release(&mut self) -> io::Result<SuspendGate> {
        self.steps.push("release");
        self.released = true;
        Ok(sample_gate())
    }
}

/// Captures every reported exit code so tests can prove EXACT propagation.
#[derive(Default)]
struct VecSink {
    reports: Vec<i32>,
}

impl ExitSink for VecSink {
    fn report(&mut self, code: i32) -> io::Result<()> {
        self.reports.push(code);
        Ok(())
    }
}

// ── run_init: the happy path proves the code is REAL ───────────────────

#[test]
fn run_init_runs_lifecycle_in_order_and_reports_exact_code() {
    let mut ops = FakeOps::spawning(42);
    let mut sink = VecSink::default();

    let rc = run_init(&mut ops, &mut sink).expect("ok");

    // (a) lifecycle order: mount → read → enter → setup → spawn.
    assert_eq!(
        ops.steps,
        vec!["mount", "read", "enter", "setup", "spawn"],
        "fixed lifecycle order"
    );
    // (b) spawns with the spec's cmd / cwd / env.
    let (cmd, cwd, env, user) = ops.spawned.expect("command was spawned");
    assert_eq!(user, None, "no user in the spec => root");
    assert_eq!(cmd, sample_spec().command);
    assert_eq!(cwd, sample_spec().cwd);
    assert_eq!(env, sample_spec().env);
    // (c) sink receives EXACTLY the spawn's exit code — not a hardcoded 0.
    assert_eq!(sink.reports, vec![42], "sink got the real exit code");
    assert_eq!(rc, 42);
}

#[test]
fn run_init_propagates_a_nonzero_code_unchanged() {
    let mut ops = FakeOps::spawning(7);
    let mut sink = VecSink::default();
    let rc = run_init(&mut ops, &mut sink).expect("ok");
    assert_eq!(rc, 7);
    assert_eq!(sink.reports, vec![7]);
}

// ── container networking: publish_ip is gated on InitSpec::net ──────────

#[test]
fn run_init_publishes_ip_when_net_enabled() {
    let mut ops = FakeOps::spawning(0);
    ops.spec.net = true;
    let mut sink = VecSink::default();

    run_init(&mut ops, &mut sink).expect("ok");

    // publish_ip runs AFTER enter + setup and BEFORE spawn (a server may block).
    assert_eq!(
        ops.steps,
        vec!["mount", "read", "enter", "setup", "publish_ip", "spawn"],
        "publish_ip is between enter and spawn"
    );
    assert!(ops.published, "the guest IP was published");
}

#[test]
fn suspend_gate_releases_before_workload_spawn() {
    let mut ops = FakeOps::spawning(0);
    ops.spec.suspend_gate = true;
    let mut sink = VecSink::default();
    run_init(&mut ops, &mut sink).expect("gated init succeeds");
    assert_eq!(
        ops.steps,
        vec!["mount", "read", "enter", "setup", "release", "spawn"]
    );
    assert!(ops.released, "gate release must precede workload spawn");
}

#[test]
fn run_init_skips_ip_when_net_disabled() {
    let mut ops = FakeOps::spawning(0); // net defaults to false
    let mut sink = VecSink::default();

    run_init(&mut ops, &mut sink).expect("ok");

    assert!(!ops.published, "no publish when net is off");
    assert!(
        !ops.steps.contains(&"publish_ip"),
        "publish_ip is not in the lifecycle when net is off"
    );
}

// ── spawn failure ⇒ 127, reported (a real outcome, not an Err) ─────────

#[test]
fn run_init_reports_127_on_spawn_failure() {
    let mut ops = FakeOps::spawn_failing();
    let mut sink = VecSink::default();

    let rc = run_init(&mut ops, &mut sink).expect("spawn failure is a real outcome");

    assert_eq!(rc, SPAWN_FAILED_CODE, "command-not-found => 127");
    assert_eq!(sink.reports, vec![SPAWN_FAILED_CODE], "127 is reported");
    assert_eq!(ops.steps, vec!["mount", "read", "enter", "setup", "spawn"]);
}

// ── mount / read / enter failure ⇒ Err, NOTHING reported ───────────────

#[test]
fn run_init_errs_on_mount_failure_and_reports_nothing() {
    let mut ops = FakeOps::failing_at("mount");
    let mut sink = VecSink::default();

    let err = run_init(&mut ops, &mut sink).expect_err("mount failure propagates");
    assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);

    assert!(sink.reports.is_empty(), "no fake code on mount failure");
    assert_eq!(ops.steps, vec!["mount"], "stopped at mount");
    assert!(ops.spawned.is_none());
}

#[test]
fn run_init_errs_on_spec_read_failure_and_reports_nothing() {
    let mut ops = FakeOps::failing_at("read");
    let mut sink = VecSink::default();

    let err = run_init(&mut ops, &mut sink).expect_err("read failure propagates");
    assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);

    assert!(sink.reports.is_empty(), "no fake code on spec-read failure");
    assert_eq!(ops.steps, vec!["mount", "read"], "stopped at read");
    assert!(ops.spawned.is_none());
}

#[test]
fn run_init_errs_on_enter_rootfs_failure_and_reports_nothing() {
    let mut ops = FakeOps::failing_at("enter");
    let mut sink = VecSink::default();

    let err = run_init(&mut ops, &mut sink).expect_err("enter failure propagates");
    assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);

    assert!(
        sink.reports.is_empty(),
        "no fake code on enter-rootfs failure"
    );
    assert_eq!(
        ops.steps,
        vec!["mount", "read", "enter"],
        "stopped at enter"
    );
    assert!(ops.spawned.is_none(), "never spawned after enter failure");
}

// ── ADR-0024 D6: the workload PID proof is gated on suspend_gate ───────

#[test]
fn ordinary_run_spawns_without_pid_proof_and_reports_real_code() {
    let mut ops = FakeOps::spawning(7);
    let mut sink = VecSink::default();
    let rc = run_init(&mut ops, &mut sink).expect("ordinary run succeeds");
    assert_eq!(
        ops.pid_proof,
        Some(None),
        "no gate ⇒ no PID proof requested"
    );
    assert_eq!((rc, sink.reports), (7, vec![7]));
}

#[test]
fn gated_run_proves_pid_with_the_released_gate() {
    let mut ops = FakeOps::spawning(0);
    ops.spec.suspend_gate = true;
    let mut sink = VecSink::default();
    run_init(&mut ops, &mut sink).expect("gated run succeeds");
    assert_eq!(ops.pid_proof, Some(Some(sample_gate())));
}

/// Guest-side half of the same fix: the Linux PID1 `spawn_wait` must take the
/// gate from its caller, never read SUSPEND_GATE_FILE itself (the file exists
/// only for suspend, so reading it failed every ordinary run with 127).
#[test]
fn guest_spawn_wait_never_reads_the_gate_file() {
    let bin = include_str!("bin/init.rs");
    let start = bin.find("fn spawn_wait(").unwrap();
    let end = start + bin[start..].find("fn publish_ip(").unwrap();
    let body = &bin[start..end];
    assert!(body.contains("if let Some(gate) = pid_proof"));
    assert!(!body.contains("SUSPEND_GATE_FILE"));
}

// ── ADR-0024 D4: guest setup, user, spawn-failure codes ────────────────

#[test]
fn setup_failure_fails_the_boot_closed() {
    let mut ops = FakeOps::failing_at("setup");
    let mut sink = VecSink::default();
    let err = run_init(&mut ops, &mut sink).expect_err("setup failure propagates");
    assert_eq!(err.kind(), io::ErrorKind::PermissionDenied);
    assert!(sink.reports.is_empty(), "no exit code after a failed setup");
    assert_eq!(ops.steps, vec!["mount", "read", "enter", "setup"]);
    assert!(ops.spawned.is_none(), "the workload never starts");
}

#[test]
fn setup_sees_the_spec_and_spawn_gets_the_user() {
    let user = GuestUser {
        uid: 1000,
        gid: 1000,
        groups: vec![1000, 27],
    };
    let mut ops = FakeOps::spawning(0);
    ops.spec.user = Some(user.clone());
    ops.spec.shm_size = Some(1 << 20);
    let mut sink = VecSink::default();
    run_init(&mut ops, &mut sink).expect("ok");
    assert_eq!(ops.setup_spec.as_ref().unwrap().shm_size, Some(1 << 20));
    assert_eq!(ops.spawned.unwrap().3, Some(user));
}

#[test]
fn spawn_failures_map_to_127_only_when_the_command_is_missing() {
    for (kind, code) in [
        (io::ErrorKind::NotFound, SPAWN_FAILED_CODE),
        (io::ErrorKind::PermissionDenied, SPAWN_DENIED_CODE),
        (io::ErrorKind::NotADirectory, SPAWN_DENIED_CODE),
    ] {
        let mut ops = FakeOps::spawning(0);
        ops.spawn_result = Err(io::Error::from(kind));
        let mut sink = VecSink::default();
        assert_eq!(run_init(&mut ops, &mut sink).unwrap(), code, "{kind:?}");
        assert_eq!(sink.reports, vec![code]);
    }
}

#[test]
fn abi1_json_parses_and_abi1_shaped_specs_serialize_unchanged() {
    let legacy = br#"{"command":["true"],"cwd":"/","env":[],"net":false,"suspend_gate":false}"#;
    let spec = InitSpec::from_json(legacy).expect("legacy json parses");
    assert_eq!(
        (spec.user.clone(), spec.volumes.len(), spec.shm_size),
        (None, 0, None)
    );
    assert_eq!(spec.to_json(), legacy.to_vec(), "no new keys when unused");
}

#[test]
fn abi2_fields_roundtrip() {
    let mut spec = sample_spec();
    spec.user = Some(GuestUser {
        uid: 1,
        gid: 2,
        groups: vec![2, 3],
    });
    spec.volumes = vec![GuestVolume {
        tag: "vol0".to_string(),
        target: "/data".to_string(),
        readonly: true,
    }];
    spec.shm_size = Some(4096);
    assert_eq!(InitSpec::from_json(&spec.to_json()).unwrap(), spec);
}

// ── the setup plan (data; bin/init.rs executes it) ─────────────────────

fn mounts(plan: &[SetupStep]) -> Vec<&GuestMount> {
    plan.iter()
        .filter_map(|s| match s {
            SetupStep::Mount(m) => Some(m),
            _ => None,
        })
        .collect()
}

#[test]
fn setup_plan_mounts_the_d4_table_in_order() {
    let plan = guest_setup_plan(None, &[]);
    let m = mounts(&plan);
    let shape: Vec<(&str, &str)> = m
        .iter()
        .map(|m| (m.fstype.as_str(), m.target.as_str()))
        .collect();
    assert_eq!(
        shape,
        vec![
            ("proc", "/proc"),
            ("sysfs", "/sys"),
            ("devtmpfs", "/dev"),
            ("devpts", "/dev/pts"),
            ("tmpfs", "/dev/shm"),
            ("tmpfs", "/tmp"),
        ]
    );
    let hardened = MountFlags {
        rdonly: false,
        nosuid: true,
        nodev: true,
        noexec: true,
    };
    assert_eq!(m[0].flags, hardened, "proc nosuid,nodev,noexec");
    assert_eq!(
        m[1].flags,
        MountFlags {
            rdonly: true,
            ..hardened
        },
        "sysfs read-only"
    );
    assert_eq!(m[3].data, "newinstance,ptmxmode=0666,mode=0620,gid=5");
    assert_eq!(m[4].data, format!("mode=1777,size={DEFAULT_SHM_BYTES}"));
    assert_eq!(m[5].data, "mode=1777");
    assert!(plan.contains(&SetupStep::Symlink {
        target: "pts/ptmx".to_string(),
        link: "/dev/ptmx".to_string(),
    }));
    assert!(plan.contains(&SetupStep::LoopbackUp));
}

#[test]
fn setup_plan_sizes_shm_from_the_run() {
    let plan = guest_setup_plan(Some(128 * 1024 * 1024), &[]);
    assert_eq!(mounts(&plan)[4].data, "mode=1777,size=134217728");
}

#[test]
fn setup_plan_mounts_volumes_last_with_their_mode() {
    let vols = [
        GuestVolume {
            tag: "vol0".to_string(),
            target: "/data".to_string(),
            readonly: true,
        },
        GuestVolume {
            tag: "vol1".to_string(),
            target: "/tmp".to_string(),
            readonly: false,
        },
    ];
    let plan = guest_setup_plan(None, &vols);
    let last: Vec<_> = plan[plan.len() - 2..].to_vec();
    let SetupStep::Mount(ro) = &last[0] else {
        panic!("volume is a mount")
    };
    assert_eq!(
        (ro.source.as_str(), ro.target.as_str(), ro.fstype.as_str()),
        ("vol0", "/data", "virtiofs")
    );
    assert!(ro.flags.rdonly, ":ro is a read-only mount");
    let SetupStep::Mount(rw) = &last[1] else {
        panic!("volume is a mount")
    };
    assert!(!rw.flags.rdonly);
    let tmp = plan
        .iter()
        .position(|s| matches!(s, SetupStep::Mount(m) if m.target == "/tmp" && m.fstype == "tmpfs"))
        .unwrap();
    assert!(tmp < plan.len() - 2, "a volume may cover the /tmp tmpfs");
}

/// The Linux executor must run every plan step and stop at the first failure;
/// it must also reap orphans (waitpid(-1)) and drop privileges in order.
#[test]
fn guest_executor_follows_the_plan_and_drops_privileges_in_order() {
    let bin = include_str!("bin/init.rs");
    let setup = &bin[bin.find("fn setup_guest(").unwrap()..];
    assert!(setup.contains("guest_setup_plan(spec.shm_size, &spec.volumes)"));
    assert!(setup.contains("describe_step(&step)"));
    let spawn = &bin[bin.find("fn spawn_wait(").unwrap()..bin.find("fn publish_ip(").unwrap()];
    let groups = spawn.find("libc::setgroups").unwrap();
    let gid = spawn.find("libc::setgid").unwrap();
    let uid = spawn.find("libc::setuid").unwrap();
    assert!(groups < gid && gid < uid, "setgroups → setgid → setuid");
    assert!(
        spawn.contains("reap_until(child.id()"),
        "no plain child.wait()"
    );
    assert!(!spawn.contains("child.wait()"));
    let sys = include_str!("bin/init_sys/mod.rs");
    let reap = &sys[sys.find("fn reap_until(").unwrap()..];
    assert!(
        reap.contains("libc::waitpid(-1"),
        "PID 1 reaps every orphan"
    );
}

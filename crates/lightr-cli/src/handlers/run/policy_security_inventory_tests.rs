use super::*;
use clap::Parser;

use crate::cli::cmd::{Cli, Cmd};
use crate::handlers::run::{HealthFlags, RawRcFlags, RawRunFlags};

struct ControlMap {
    control: &'static str,
    cli: &'static str,
    parser: &'static str,
    run_config: &'static str,
    exec_spec: Option<&'static str>,
    witness: &'static str,
}

// Closed parser -> RcConfig -> RunSpec/ExecSpec lowering inventory. Keep this
// beside lowering code: changing either side must break this test.
const CONTROLS: &[ControlMap] = &[
    ControlMap {
        control: "user",
        cli: "--user",
        parser: "RunArgs.user",
        run_config: "user",
        exec_spec: Some("user"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "hostname",
        cli: "--hostname",
        parser: "RawRcFlags.hostname",
        run_config: "hostname",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::build_detached_spec",
    },
    ControlMap {
        control: "labels",
        cli: "--label",
        parser: "RawRcFlags.label",
        run_config: "labels",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::build_detached_spec",
    },
    ControlMap {
        control: "tty",
        cli: "--tty",
        parser: "RawRcFlags.tty",
        run_config: "tty",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::build_detached_spec",
    },
    ControlMap {
        control: "init",
        cli: "--init",
        parser: "RawRcFlags.init",
        run_config: "init",
        exec_spec: Some("init"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "privileged",
        cli: "--privileged",
        parser: "RawRcFlags.privileged",
        run_config: "privileged",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::rc_privileged_policy",
    },
    ControlMap {
        control: "read_only",
        cli: "--read-only",
        parser: "RawRcFlags.read_only",
        run_config: "read_only",
        exec_spec: Some("read_only"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "cap_add",
        cli: "--cap-add",
        parser: "RawRcFlags.cap_add",
        run_config: "cap_add",
        exec_spec: Some("cap_add"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "cap_drop",
        cli: "--cap-drop",
        parser: "RawRcFlags.cap_drop",
        run_config: "cap_drop",
        exec_spec: Some("cap_drop"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "seccomp",
        cli: "--seccomp",
        parser: "RawRcFlags.seccomp",
        run_config: "seccomp",
        exec_spec: Some("seccomp"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "apparmor",
        cli: "--apparmor",
        parser: "RawRcFlags.apparmor",
        run_config: "apparmor",
        exec_spec: Some("apparmor"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "memory_limit",
        cli: "--memory",
        parser: "RunArgs.memory",
        run_config: "limits.memory_bytes",
        exec_spec: Some("limits"),
        witness: "crates/lightr-cli/src/handlers/run/mod.rs::ResourceLimits::parse",
    },
    ControlMap {
        control: "cpu_limit",
        cli: "--cpus",
        parser: "RunArgs.cpus",
        run_config: "limits.cpu_millis",
        exec_spec: Some("limits"),
        witness: "crates/lightr-cli/src/handlers/run/mod.rs::ResourceLimits::parse",
    },
    ControlMap {
        control: "pids_limit",
        cli: "--pids-limit",
        parser: "RawRcFlags.pids_limit",
        run_config: "limits.pids_max",
        exec_spec: Some("limits"),
        witness: "crates/lightr-core/src/core/limits.rs::ResourceLimits::with_pids",
    },
    ControlMap {
        control: "ulimit",
        cli: "--ulimit",
        parser: "RawRunFlags.ulimit",
        run_config: "ulimits",
        exec_spec: Some("ulimits"),
        witness: "crates/lightr-cli/src/handlers/run/mod.rs::parse_ulimits",
    },
    ControlMap {
        control: "oom_score_adj",
        cli: "--oom-score-adj",
        parser: "RawRcFlags.oom_score_adj",
        run_config: "oom_score_adj",
        exec_spec: Some("oom_score_adj"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "shm_size",
        cli: "--shm-size",
        parser: "RawRcFlags.shm_size",
        run_config: "shm_size",
        exec_spec: Some("shm_size"),
        witness: "crates/lightr-cli/src/handlers/run/paths.rs::run_engine",
    },
    ControlMap {
        control: "tmpfs",
        cli: "--tmpfs",
        parser: "RawRunFlags.tmpfs",
        run_config: "tmpfs",
        exec_spec: Some("tmpfs"),
        witness: "crates/lightr-cli/src/handlers/run/mod.rs::parse_tmpfs",
    },
    ControlMap {
        control: "network_mode",
        cli: "--net",
        parser: "RunArgs.net",
        run_config: "net_isolate",
        exec_spec: Some("net_isolate"),
        witness: "crates/lightr-cli/src/handlers/run/flags.rs::resolve_net_isolate",
    },
    ControlMap {
        control: "add_host",
        cli: "--add-host",
        parser: "RawRunFlags.add_host",
        run_config: "add_host",
        exec_spec: Some("add_host"),
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::resolve_add_host_pairs",
    },
    ControlMap {
        control: "healthcheck",
        cli: "--health-*",
        parser: "HealthFlags",
        run_config: "healthcheck",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/flags.rs::HealthFlags",
    },
    ControlMap {
        control: "secret",
        cli: "--secret",
        parser: "RunArgs.secret",
        run_config: "secrets",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::resolve_store_files",
    },
    ControlMap {
        control: "config",
        cli: "--config",
        parser: "RunArgs.config",
        run_config: "configs",
        exec_spec: None,
        witness: "crates/lightr-cli/src/handlers/run/policy.rs::resolve_store_files",
    },
];

fn resolve_witness(path: &str, symbol: &str) -> Result<(), String> {
    match (path, symbol) {
        ("crates/lightr-cli/src/handlers/run/paths.rs", "run_engine") => {
            let _ = super::super::paths::run_engine;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/policy.rs", "build_detached_spec") => {
            let _ = build_detached_spec;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/policy.rs", "rc_privileged_policy") => {
            let _ = rc_privileged_policy;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/mod.rs", "ResourceLimits::parse") => {
            let _ = ResourceLimits::parse;
            Ok(())
        }
        ("crates/lightr-core/src/core/limits.rs", "ResourceLimits::with_pids") => {
            let _ = ResourceLimits::with_pids;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/mod.rs", "parse_ulimits") => {
            let _ = super::super::parse_ulimits;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/mod.rs", "parse_tmpfs") => {
            let _ = super::super::parse_tmpfs;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/flags.rs", "resolve_net_isolate") => {
            let _ = super::super::resolve_net_isolate;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/policy.rs", "resolve_add_host_pairs") => {
            let _ = resolve_add_host_pairs;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/flags.rs", "HealthFlags") => {
            let _ = HealthFlags::build;
            Ok(())
        }
        ("crates/lightr-cli/src/handlers/run/policy.rs", "resolve_store_files") => {
            let _ = resolve_store_files;
            Ok(())
        }
        (unknown, _) if !unknown.starts_with("crates/lightr-cli/src/") => {
            Err(format!("witness path not declared: {unknown}"))
        }
        (path, symbol) => Err(format!("witness symbol not declared: {path}::{symbol}")),
    }
}

fn validate_inventory(inventory: &serde_json::Value) -> Result<(), String> {
    let rows = inventory["controls"].as_array().ok_or("missing controls")?;
    if rows.len() != CONTROLS.len() {
        return Err(format!(
            "expected {} controls, got {}",
            CONTROLS.len(),
            rows.len()
        ));
    }
    for map in CONTROLS {
        debug_assert!(!map.witness.is_empty());
        let row = rows
            .iter()
            .find(|row| row["control"] == map.control)
            .ok_or_else(|| format!("missing control: {}", map.control))?;
        for (key, expected) in [
            ("cli", map.cli),
            ("parser", map.parser),
            ("run_config", map.run_config),
        ] {
            if row[key].as_str() != Some(expected) {
                return Err(format!("{} has wrong {key}", map.control));
            }
        }
        if row["exec_spec"].as_str() != map.exec_spec {
            return Err(format!("{} has wrong exec_spec", map.control));
        }
        for field in ["enforcement", "platform", "oracle", "fixture", "mutation"] {
            if row[field].as_str().is_none_or(str::is_empty) {
                return Err(format!("{} missing {field}", map.control));
            }
        }
        let witness = row["witness"]
            .as_str()
            .ok_or_else(|| format!("{} witness is not a string", map.control))?;
        let (path, symbol) = witness
            .split_once("::")
            .ok_or_else(|| format!("{} witness has no path::symbol", map.control))?;
        resolve_witness(path, symbol).map_err(|error| format!("{} {error}", map.control))?;
        for engine in ["native", "ns", "vz"] {
            if !matches!(
                row[engine].as_str(),
                Some("enforced" | "refused" | "unsupported")
            ) {
                return Err(format!("{}/{engine} has no typed outcome", map.control));
            }
        }
    }
    Ok(())
}

#[test]
fn inventory_matches_closed_lowering_map_and_resolvable_witnesses() {
    let inventory: serde_json::Value =
        serde_json::from_str(include_str!("policy_security_inventory.json")).unwrap();
    validate_inventory(&inventory).unwrap();
}

#[test]
fn inventory_validator_rejects_mapping_and_witness_mutations() {
    let mut inventory: serde_json::Value =
        serde_json::from_str(include_str!("policy_security_inventory.json")).unwrap();
    inventory["controls"][0]["cli"] = serde_json::Value::String("--mutated".into());
    assert!(validate_inventory(&inventory).is_err());
    inventory["controls"][0]["cli"] = serde_json::Value::String("--user".into());
    inventory["controls"][0]["witness"] = serde_json::Value::String("missing.rs::eff_user".into());
    assert_eq!(
        validate_inventory(&inventory),
        Err("user witness path not declared: missing.rs".into())
    );
    inventory["controls"][0]["witness"] =
        serde_json::Value::String("crates/lightr-cli/src/handlers/run/paths.rs::gone".into());
    assert_eq!(
        validate_inventory(&inventory),
        Err(
            "user witness symbol not declared: crates/lightr-cli/src/handlers/run/paths.rs::gone"
                .into()
        )
    );
}

#[test]
fn cli_parser_lowers_all_security_controls_through_production_conversions() {
    let cli = Cli::try_parse_from([
        "lightr",
        "run",
        "--user",
        "1000",
        "--hostname",
        "host",
        "--label",
        "key=value",
        "--tty",
        "--init",
        "--privileged",
        "--read-only",
        "--cap-add",
        "NET_BIND_SERVICE",
        "--cap-drop",
        "ALL",
        "--seccomp",
        "profile.json",
        "--apparmor",
        "profile",
        "--memory",
        "64m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "16",
        "--ulimit",
        "nofile=64",
        "--oom-score-adj",
        "100",
        "--shm-size",
        "64m",
        "--tmpfs",
        "/scratch",
        "--net",
        "none",
        "--add-host",
        "host:127.0.0.1",
        "--health-cmd",
        "true",
        "--secret",
        "sec=ref",
        "--config",
        "cfg=ref",
        "--",
        "true",
    ])
    .unwrap();
    let Cmd::Run(args) = cli.cmd else {
        panic!("expected run")
    };
    let rc = RawRcFlags::from(&args).resolve().unwrap();
    let raw_runflags = RawRunFlags::from(&args);
    let health = HealthFlags::from(&args);
    let limits = ResourceLimits::parse(args.memory.as_deref(), args.cpus.as_deref())
        .unwrap()
        .with_pids(rc.pids_limit);
    let secrets = resolve_store_files(&args.secret, "secret").unwrap();
    let configs = resolve_store_files(&args.config, "config").unwrap();
    let net = super::super::flags::resolve_net_isolate(&args.net, false).unwrap();
    let runflags = raw_runflags.resolve().unwrap();
    let add_host = resolve_add_host_pairs(&runflags);
    let spec = build_detached_spec(
        std::path::PathBuf::from("/work"),
        &[],
        &[],
        vec![],
        secrets,
        configs,
        vec![],
        vec![],
        None,
        args.user.as_deref(),
        None,
        None,
        limits,
        &rc,
        &runflags,
    );
    assert_eq!(spec.hostname.as_deref(), Some("host"));
    assert_eq!(spec.labels, vec![("key".to_string(), "value".to_string())]);
    assert_eq!(spec.cap_add, ["NET_BIND_SERVICE"]);
    assert_eq!(spec.cap_drop, ["ALL"]);
    assert!(spec.privileged && spec.tty && spec.init && spec.read_only);
    assert_eq!(spec.oom_score_adj, Some(100));
    assert_eq!(spec.pids_limit, Some(16));
    assert_eq!(spec.shm_size, Some(64 * 1024 * 1024));
    assert_eq!(spec.user.as_deref(), Some("1000"));
    assert_eq!(spec.limits.cpu_millis, Some(500));
    assert_eq!(spec.limits.memory_bytes, Some(64 * 1024 * 1024));
    assert_eq!(spec.limits.pids_max, Some(16));
    assert_eq!(spec.secrets.len(), 1);
    assert_eq!(spec.configs.len(), 1);
    assert_eq!(runflags.tmpfs, ["/scratch"]);
    assert_eq!(runflags.ulimit, ["nofile=64"]);
    assert_eq!(rc.apparmor.as_deref(), Some("profile"));
    assert_eq!(rc.seccomp.as_deref(), Some("profile.json"));
    let tmpfs = super::super::parse_tmpfs(&runflags.tmpfs).unwrap();
    let ulimits = super::super::parse_ulimits(&runflags.ulimit).unwrap();
    let command = vec!["true".to_string()];
    let env = vec![];
    let exec = super::super::paths::build_exec_spec(
        std::path::Path::new("/work"),
        &command,
        None,
        limits,
        net,
        &env,
        args.user.as_deref(),
        &add_host,
        rc.read_only,
        rc.shm_size,
        &rc.cap_drop,
        &rc.cap_add,
        rc.init,
        rc.apparmor.as_deref(),
        rc.seccomp.as_deref(),
        &tmpfs,
        &ulimits,
        rc.oom_score_adj,
    );
    let mut captured = None;
    let mut basics = None;
    assert_eq!(
        super::super::paths::run_engine_with(&exec, |spec| {
            basics = Some((
                spec.cwd.to_path_buf(),
                spec.command.to_vec(),
                spec.rootfs.map(std::path::Path::to_path_buf),
                spec.limits,
                spec.env.to_vec(),
                spec.user.map(str::to_owned),
            ));
            captured = Some((
                spec.read_only,
                spec.init,
                spec.net_isolate,
                spec.shm_size,
                spec.cap_add.to_vec(),
                spec.cap_drop.to_vec(),
                spec.seccomp.map(str::to_owned),
                spec.apparmor.map(str::to_owned),
                spec.tmpfs.to_vec(),
                spec.ulimits.to_vec(),
                spec.oom_score_adj,
                spec.add_host.to_vec(),
                spec.net,
                spec.net_fd,
                spec.net_mac,
                spec.mounts.len(),
                spec.workdir.map(str::to_owned),
                spec.hostname.map(str::to_owned),
                spec.dns.len(),
                spec.mesh_ip,
                spec.join_netns.is_none(),
                spec.cgroup_name.map(str::to_owned),
                spec.exec_ready_fd,
                spec.bind_mounts.len(),
                spec.resolv_conf.map(str::to_owned),
            ));
            0
        }),
        0
    );
    let captured = captured.unwrap();
    let basics = basics.unwrap();
    assert_eq!(basics.0, std::path::PathBuf::from("/work"));
    assert_eq!(basics.1, ["true"]);
    assert!(basics.2.is_none());
    assert_eq!(basics.3.memory_bytes, Some(64 * 1024 * 1024));
    assert_eq!(basics.3.cpu_millis, Some(500));
    assert_eq!(basics.3.pids_max, Some(16));
    assert!(basics.4.is_empty());
    assert_eq!(basics.5.as_deref(), Some("1000"));
    assert!(captured.0 && captured.1 && captured.2);
    assert_eq!(captured.3, Some(64 * 1024 * 1024));
    assert_eq!(captured.4, ["NET_BIND_SERVICE"]);
    assert_eq!(captured.5, ["ALL"]);
    assert_eq!(captured.6.as_deref(), Some("profile.json"));
    assert_eq!(captured.7.as_deref(), Some("profile"));
    assert_eq!(captured.8.len(), 1);
    assert_eq!(captured.8[0].target, "/scratch");
    assert_eq!(captured.8[0].size, None);
    assert_eq!(captured.8[0].mode, "1777");
    assert_eq!(captured.9.len(), 1);
    assert_eq!(captured.9[0].resource, 7);
    assert_eq!(captured.9[0].soft, 64);
    assert_eq!(captured.9[0].hard, 64);
    assert_eq!(captured.10, Some(100));
    assert_eq!(captured.11, [("host".to_string(), "127.0.0.1".to_string())]);
    assert!(!captured.12 && captured.13.is_none() && captured.14.is_none());
    assert_eq!(captured.15, 0);
    assert!(captured.16.is_none() && captured.17.is_none());
    assert_eq!(captured.18, 0);
    assert!(captured.19.is_none() && captured.20 && captured.21.is_none());
    assert!(captured.22.is_none());
    assert_eq!(captured.23, 0);
    assert!(captured.24.is_none());
    assert!(health.build().is_some());
    assert!(net);
    assert_eq!(add_host, [("host".to_string(), "127.0.0.1".to_string())]);
    let mut apparmor_only = rc.clone();
    apparmor_only.seccomp = None;
    assert_eq!(
        engine_capability_policy(EngineKind::Ns, &apparmor_only),
        None
    );
    assert_eq!(
        engine_capability_policy(EngineKind::Ns, &rc),
        seccomp_arch_policy(
            rc.seccomp.as_deref(),
            cfg!(any(target_arch = "x86_64", target_arch = "aarch64")),
        )
    );
    assert_eq!(engine_capability_policy(EngineKind::Native, &rc), Some(2));
}

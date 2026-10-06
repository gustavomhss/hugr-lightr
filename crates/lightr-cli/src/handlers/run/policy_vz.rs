//! ADR-0024: refuse the `lightr run` flags the `vz` engine does not apply.
//!
//! Since D4 both vz paths (detached supervisor `lightr-run/src/run/svz.rs`,
//! foreground memo path `paths_vz.rs`) hand the engine the resolved env, user,
//! workdir, `-v` host directories and `--shm-size`, and the guest init applies
//! them (`lightr_engine::engine::vzguest`). Still dropped, so still an honest
//! exit 2 before provisioning (CLAUDE.md principle 7): `--env KEY` (host-env
//! memo keys; the guest does not inherit the host env), named volumes,
//! `--mount` CAS refs, `--hostname`, `--dns`, `--add-host`.

use lightr_engine::EngineKind;

use super::runflags::RunFlags;
use super::RcConfig;

/// The raw `lightr run` inputs the vz policy judges. `-e`, `--env-file`, `-u`
/// and `-w` are applied (D4), so they are no longer inputs here.
pub(super) struct VzFlagInputs<'a> {
    pub env_keys: &'a [String],
    pub mounts_raw: &'a [String],
    pub runflags: &'a RunFlags,
    pub rc: &'a RcConfig,
}

/// `Some(2)` when `engine` is vz and any unapplied flag is set; `None` otherwise.
pub(super) fn vz_unapplied_flags_policy(engine: EngineKind, inputs: &VzFlagInputs) -> Option<i32> {
    let flag = vz_unapplied_flag(engine, inputs)?;
    eprintln!(
        "lightr: {flag} is not applied on the vz engine yet (the guest init does not \
         receive it; ADR-0024); refusing to run rather than drop it silently"
    );
    Some(2)
}

/// The first set flag that vz would drop, named as the user typed it.
fn vz_unapplied_flag(engine: EngineKind, inputs: &VzFlagInputs) -> Option<&'static str> {
    if engine != EngineKind::Vz {
        return None;
    }
    let refused = [
        (!inputs.env_keys.is_empty(), "--env"),
        (
            !inputs.runflags.named_volumes.is_empty(),
            "-v/--volume with a named volume",
        ),
        (!inputs.mounts_raw.is_empty(), "--mount"),
        (inputs.rc.hostname.is_some(), "--hostname"),
        (!inputs.runflags.dns.is_empty(), "--dns"),
        (!inputs.runflags.add_host.is_empty(), "--add-host"),
    ];
    refused
        .into_iter()
        .find(|(set, _)| *set)
        .map(|(_, flag)| flag)
}

/// `Some(2)` when the spec needs `init_abi` 2 (`-u`/image USER, `-v`,
/// `--shm-size`) and the installed pack's init is older. No pack ⇒ `None`
/// (the engine's own "vz unavailable" error speaks then).
pub(super) fn vz_init_abi_policy(needs_abi2: bool) -> Option<i32> {
    let dir = lightr_engine::pack::installed_pack_dir();
    if !needs_abi2 || !dir.join("initrd").exists() {
        return None;
    }
    lightr_engine::pack::require_init_abi(&dir, lightr_engine::INIT_ABI)
        .err()
        .map(|e| crate::exit::die_lightr(&e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::handlers::run::RawRunFlags;

    fn inputs<'a>(runflags: &'a RunFlags, rc: &'a RcConfig) -> VzFlagInputs<'a> {
        VzFlagInputs {
            env_keys: &[],
            mounts_raw: &[],
            runflags,
            rc,
        }
    }

    static NO_RUNFLAGS: std::sync::LazyLock<RunFlags> = std::sync::LazyLock::new(RunFlags::default);
    static NO_RC: std::sync::LazyLock<RcConfig> = std::sync::LazyLock::new(RcConfig::default);

    /// The flag `engine` refuses for the default inputs after `edit`.
    fn refused<'a>(
        engine: EngineKind,
        edit: impl FnOnce(&mut VzFlagInputs<'a>),
    ) -> Option<&'static str> {
        let mut set = inputs(&NO_RUNFLAGS, &NO_RC);
        edit(&mut set);
        vz_unapplied_flag(engine, &set)
    }

    #[test]
    fn no_flags_run_on_vz() {
        assert_eq!(refused(EngineKind::Vz, |_| {}), None);
    }

    #[test]
    fn env_keys_are_still_refused_on_vz() {
        let keys = ["HOME".to_string()];
        assert_eq!(
            refused(EngineKind::Vz, |i| i.env_keys = &keys),
            Some("--env")
        );
    }

    #[test]
    fn host_dir_volumes_pass_named_volumes_and_mounts_are_refused_on_vz() {
        let rc = RcConfig::default();
        for (volume, expected) in [
            ("/tmp:/data:ro", None),
            ("cache:/cache", Some("-v/--volume with a named volume")),
        ] {
            let runflags = RawRunFlags {
                volume: vec![volume.to_string()],
                ..RawRunFlags::default()
            }
            .resolve()
            .unwrap();
            assert_eq!(
                vz_unapplied_flag(EngineKind::Vz, &inputs(&runflags, &rc)),
                expected,
                "{volume}"
            );
        }
        let mounts = ["ref:target".to_string()];
        assert_eq!(
            refused(EngineKind::Vz, |i| i.mounts_raw = &mounts),
            Some("--mount")
        );
    }

    #[test]
    fn hostname_dns_and_add_host_are_refused_on_vz() {
        let empty = RunFlags::default();
        let rc = RcConfig {
            hostname: Some("box".to_string()),
            ..RcConfig::default()
        };
        assert_eq!(
            vz_unapplied_flag(EngineKind::Vz, &inputs(&empty, &rc)),
            Some("--hostname")
        );
        let rc = RcConfig::default();
        let dns = RunFlags {
            dns: vec!["1.1.1.1".to_string()],
            ..RunFlags::default()
        };
        assert_eq!(
            vz_unapplied_flag(EngineKind::Vz, &inputs(&dns, &rc)),
            Some("--dns")
        );
        let hosts = RunFlags {
            add_host: vec!["db:10.0.0.2".to_string()],
            ..RunFlags::default()
        };
        assert_eq!(
            vz_unapplied_flag(EngineKind::Vz, &inputs(&hosts, &rc)),
            Some("--add-host")
        );
    }

    #[test]
    fn other_engines_are_not_judged_here() {
        let env = ["K=V".to_string()];
        for engine in [EngineKind::Native, EngineKind::Ns, EngineKind::Wsl] {
            assert_eq!(refused(engine, |i| i.env_keys = &env), None);
        }
    }

    #[test]
    fn policy_exits_2_only_when_a_flag_is_refused() {
        let (runflags, rc) = (RunFlags::default(), RcConfig::default());
        let mut set = inputs(&runflags, &rc);
        assert_eq!(vz_unapplied_flags_policy(EngineKind::Vz, &set), None);
        let mounts = ["ref:target".to_string()];
        set.mounts_raw = &mounts;
        assert_eq!(vz_unapplied_flags_policy(EngineKind::Vz, &set), Some(2));
    }

    /// Wiring: `run()` refuses before any store/provisioning work, on the
    /// foreground (memo) and detached (supervisor) vz paths alike.
    #[test]
    fn run_refuses_vz_flags_on_foreground_and_detached_paths() {
        use crate::handlers::run::{run, HealthFlags, RawRcFlags};
        let keys = ["HOME".to_string()];
        for detach in [false, true] {
            let code = run(
                ".",
                &[],
                &keys, // --env (host-env memo keys): still dropped on vz
                &["true".to_string()],
                false,
                false,
                detach,
                &[],
                false,
                &[],
                "vz",
                Some("alpine"),
                "host",
                false,
                None,
                None,
                &[],
                &[],
                &[],
                None,
                None,
                None,
                None,
                None,
                &HealthFlags::default(),
                RawRcFlags::default(),
                RawRunFlags::default(),
            );
            assert_eq!(code, 2, "vz --env must exit 2 (detach={detach})");
        }
    }
}

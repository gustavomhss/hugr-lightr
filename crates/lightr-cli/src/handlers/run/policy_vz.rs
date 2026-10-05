//! ADR-0024 stage 2: refuse the `lightr run` flags the `vz` engine does not apply.
//!
//! Both vz paths hand the engine an empty env/user/mounts/workdir (detached
//! supervisor `lightr-run/src/run/svz.rs`, foreground memo path `paths_vz.rs`),
//! and `VzEngine::run` writes a guest env of `PATH` only, cwd `/`, and ignores the
//! hostname/DNS/hosts fields. Until the guest init applies them (ADR-0024 stages
//! 3-4), each such flag is an honest exit 2 before provisioning, never a silent
//! drop (CLAUDE.md principle 7).

use lightr_engine::EngineKind;

use super::runflags::RunFlags;
use super::RcConfig;

/// The raw `lightr run` inputs that the vz engine drops today.
pub(super) struct VzFlagInputs<'a> {
    pub env_set: &'a [String],
    pub env_file: Option<&'a str>,
    pub env_keys: &'a [String],
    pub user: Option<&'a str>,
    pub workdir: Option<&'a str>,
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
        (!inputs.env_set.is_empty(), "-e"),
        (inputs.env_file.is_some(), "--env-file"),
        (!inputs.env_keys.is_empty(), "--env"),
        (inputs.user.is_some(), "-u/--user"),
        (
            !inputs.runflags.volumes.is_empty() || !inputs.runflags.named_volumes.is_empty(),
            "-v/--volume",
        ),
        (!inputs.mounts_raw.is_empty(), "--mount"),
        (inputs.workdir.is_some(), "-w/--workdir"),
        (inputs.rc.hostname.is_some(), "--hostname"),
        (!inputs.runflags.dns.is_empty(), "--dns"),
        (!inputs.runflags.add_host.is_empty(), "--add-host"),
    ];
    refused
        .into_iter()
        .find(|(set, _)| *set)
        .map(|(_, flag)| flag)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::handlers::run::RawRunFlags;

    fn inputs<'a>(runflags: &'a RunFlags, rc: &'a RcConfig) -> VzFlagInputs<'a> {
        VzFlagInputs {
            env_set: &[],
            env_file: None,
            env_keys: &[],
            user: None,
            workdir: None,
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
    fn env_flags_are_refused_on_vz() {
        let env = ["K=V".to_string()];
        let keys = ["HOME".to_string()];
        assert_eq!(refused(EngineKind::Vz, |i| i.env_set = &env), Some("-e"));
        assert_eq!(
            refused(EngineKind::Vz, |i| i.env_file = Some("f.env")),
            Some("--env-file")
        );
        assert_eq!(
            refused(EngineKind::Vz, |i| i.env_keys = &keys),
            Some("--env")
        );
    }

    #[test]
    fn user_and_workdir_are_refused_on_vz() {
        assert_eq!(
            refused(EngineKind::Vz, |i| i.user = Some("1000:1000")),
            Some("-u/--user")
        );
        assert_eq!(
            refused(EngineKind::Vz, |i| i.workdir = Some("/srv")),
            Some("-w/--workdir")
        );
    }

    #[test]
    fn volumes_and_mounts_are_refused_on_vz() {
        let rc = RcConfig::default();
        for volume in ["/tmp:/data:ro", "cache:/cache"] {
            let runflags = RawRunFlags {
                volume: vec![volume.to_string()],
                ..RawRunFlags::default()
            }
            .resolve()
            .unwrap();
            assert_eq!(
                vz_unapplied_flag(EngineKind::Vz, &inputs(&runflags, &rc)),
                Some("-v/--volume"),
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
            assert_eq!(refused(engine, |i| i.env_set = &env), None);
            assert_eq!(refused(engine, |i| i.user = Some("1000")), None);
        }
    }

    #[test]
    fn policy_exits_2_only_when_a_flag_is_refused() {
        let (runflags, rc) = (RunFlags::default(), RcConfig::default());
        let mut set = inputs(&runflags, &rc);
        assert_eq!(vz_unapplied_flags_policy(EngineKind::Vz, &set), None);
        set.workdir = Some("/srv");
        assert_eq!(vz_unapplied_flags_policy(EngineKind::Vz, &set), Some(2));
    }

    /// Wiring: `run()` refuses before any store/provisioning work, on the
    /// foreground (memo) and detached (supervisor) vz paths alike.
    #[test]
    fn run_refuses_vz_flags_on_foreground_and_detached_paths() {
        use crate::handlers::run::{run, HealthFlags, RawRcFlags};
        let env = ["K=V".to_string()];
        for detach in [false, true] {
            let code = run(
                ".",
                &[],
                &[],
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
                &env, // -e
                None,
                Some("/srv"), // -w
                None,
                None,
                None,
                &HealthFlags::default(),
                RawRcFlags::default(),
                RawRunFlags::default(),
            );
            assert_eq!(code, 2, "vz -e/-w must exit 2 (detach={detach})");
        }
    }
}

//! lightr-engine submodules — Engine trait, dispatch, and all engine impls.

pub mod envuser;
pub mod kind;
pub mod native;
pub mod ns;
pub mod probe;
// WP-#108 (seccomp): OCI seccomp profile → cBPF compiler + apply, consumed by the
// `ns` engine (PID 1). Each supported architecture selects its own audit value and
// syscall table. Other Linux architectures reject `--seccomp` before provisioning
// and in PID 1: never a silent unfiltered run.
#[cfg(all(
    target_os = "linux",
    any(target_arch = "x86_64", target_arch = "aarch64")
))]
pub(crate) mod seccomp;
pub mod spec;
// WP-#114: rootless subuid/subgid RANGE resolution (real non-root `--user`),
// consumed by the `ns` engine. Pure std (parse + helper-find); Linux-only because
// only the `ns` engine uses it (gating avoids dead-code on other targets).
#[cfg(target_os = "linux")]
pub(crate) mod subid;
pub mod vz;
/// ADR-0024 D4 host half: the guest spec a vz boot applies.
pub mod vzguest;
pub mod wsl;

pub use kind::{EngineCaps, EngineKind};
pub use native::NativeEngine;
pub use probe::{pack_status, probe};
pub use spec::{BindMount, ExecSpec, MountKind, ResolvedMount, TmpfsMount, Ulimit};

use lightr_core::{LightrError, Result};
use std::path::PathBuf;

/// Snapshot artifact created before a lazy compose listener binds.
///
/// `instance_id` and `artifact_sha256` are durable identity: a resume must
/// restore this exact artifact, never create a replacement workload.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SuspendedArtifact {
    pub instance_id: String,
    pub artifact_sha256: String,
    pub snapshot_path: PathBuf,
    pub state_path: PathBuf,
    pub machine_id: String,
    pub config_sha256: String,
    // Authority and rootfs identity never leave the retained owner protocol.
    pub(crate) release_token: String,
    pub(crate) rootfs: PathBuf,
}

impl SuspendedArtifact {
    /// Retained local rootfs, never serialized into compose state or receipts.
    pub fn rootfs(&self) -> &std::path::Path {
        &self.rootfs
    }
}

/// Result of attempting to suspend a workload. Unsupported is data, not a
/// cold-spawn permission; compose must surface it and bind no lazy listener.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SuspendResume {
    Suspended(SuspendedArtifact),
    Unsupported { engine: EngineKind, reason: String },
}

/// Restored workload identity. `pid` appears only after real snapshot restore.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResumedInstance {
    pub instance_id: String,
    pub artifact_sha256: String,
    pub pid: u32,
}

// ── Engine trait ──────────────────────────────────────────────────────────────

pub trait Engine: Send {
    /// Spawn + wait; stdout/stderr inherit. Exit law: code or 128+signal.
    fn run(&self, spec: &ExecSpec) -> Result<i32>;

    /// Create a restorable suspended artifact. Engines without real snapshot
    /// support return `SuspendResume::Unsupported`; they must not emulate it by
    /// deferring a normal spawn.
    fn suspend(&self, _spec: &ExecSpec, _artifact_dir: &std::path::Path) -> Result<SuspendResume> {
        Ok(SuspendResume::Unsupported {
            engine: self.kind(),
            reason: "engine has no real snapshot suspend/resume support".to_string(),
        })
    }

    /// Restore an artifact created by `suspend`. Implementations must reject a
    /// different machine, configuration, identity, or artifact digest.
    fn resume(&self, _artifact: &SuspendedArtifact) -> Result<ResumedInstance> {
        Err(LightrError::Unsupported(format!(
            "engine {:?} has no real snapshot resume support",
            self.kind()
        )))
    }

    /// Release retained engine state before its snapshot artifacts disappear.
    fn teardown(&self) {}

    fn kind(&self) -> EngineKind;
}

// ── engine_for ────────────────────────────────────────────────────────────────

/// Unavailable ⇒ Err(InvalidRef("engine <kind>: <probe detail>")).
pub fn engine_for(kind: EngineKind) -> Result<Box<dyn Engine>> {
    let caps = probe(kind);
    if !caps.available {
        return Err(LightrError::InvalidRef(format!(
            "engine {:?}: {}",
            kind, caps.detail
        )));
    }
    match kind {
        EngineKind::Native => Ok(Box::new(NativeEngine)),
        EngineKind::Ns => Ok(ns::ns_engine_box()),
        EngineKind::Vz => Ok(vz::vz_engine_box()),
        EngineKind::Wsl => Ok(wsl::wsl_engine_box()),
    }
}

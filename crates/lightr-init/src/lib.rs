//! lightr-init — the Linux guest's PID 1 (build-spec-prod.md §WP-B-init,
//! reworked 2026-06-12 for the real macOS `vz` boot).
//!
//! The LIBRARY is host-portable and fully unit-tested: the init lifecycle is
//! parameterized over [`GuestOps`] (mount / read-spec / enter-rootfs / spawn)
//! and [`ExitSink`] (exit-code report), so it runs on Intel/macOS today. The
//! real Linux syscalls live in `bin/init.rs` behind `#[cfg(target_os="linux")]`.
//!
//! ## Channel design (why files, not vsock/cmdline)
//!
//! macOS has NO host `AF_VSOCK`, and the kernel cmdline cannot carry args with
//! spaces (`sh -c 'exit 7'`) without bespoke quoting. So the host↔guest channel
//! is two small files on the **shared, writable** rootfs virtiofs share:
//!   - host writes the command [`InitSpec`] JSON to [`CMD_FILE`] before boot;
//!   - guest reads it, runs the command, writes the REAL exit code to
//!     [`EXIT_FILE`]; the host reads that back after the VM stops.
//!
//! The lifecycle never synthesizes a success — `sink.report()` always receives
//! the actual `spawn_wait` result (or 127 when the command cannot be spawned).

use serde::{Deserialize, Serialize};

/// virtiofs tag for the rootfs share (matches the Swift shim's `rootfs` tag).
pub const ROOTFS_TAG: &str = "rootfs";
/// Mount target for the rootfs virtiofs share (before chroot).
pub const ROOTFS_DEST: &str = "/newroot";

/// Command file: the host writes the [`InitSpec`] JSON here on the rootfs share
/// (so the guest sees it at `ROOTFS_DEST` + `CMD_FILE` before chroot). Replaces
/// kernel-cmdline `LIGHTR_CMD` (which cannot carry spaces). Must match
/// `CMD_FILE_NAME` in crates/lightr-engine/src/lib.rs (vz_impl).
pub const CMD_FILE: &str = "/.lightr-cmd";

/// Exit file: the guest writes its REAL exit code as a decimal integer here (on
/// the rootfs share, after chroot → rootfs root); the host reads it back after
/// the VM stops. The macOS `vz` exit channel (no host AF_VSOCK). Must match
/// `EXIT_FILE_NAME` in crates/lightr-engine/src/lib.rs (vz_impl).
pub const EXIT_FILE: &str = "/.lightr-exit-code";

/// Stdout capture file: the guest redirects the command's stdout here (on the
/// rootfs share, after chroot → rootfs root). The host reads it back after the
/// VM stops so the run can be MEMOIZED exactly like the native path — the vz
/// memo replays {exit, stdout, stderr} from the Action Cache on a HIT. The
/// macOS `vz` output channel (no host AF_VSOCK), the sibling of [`EXIT_FILE`].
pub const STDOUT_FILE: &str = "/.lightr-stdout";

/// Stderr capture file: the guest redirects the command's stderr here (on the
/// rootfs share, after chroot → rootfs root). The host reads it back after the
/// VM stops for the vz memo (replayed on a HIT). The sibling of [`STDOUT_FILE`]
/// / [`EXIT_FILE`].
pub const STDERR_FILE: &str = "/.lightr-stderr";

/// IP file: when networking is enabled ([`InitSpec::net`]), the guest writes its
/// primary non-loopback IPv4 (decimal dotted-quad, no trailing newline) here, on
/// the rootfs share after chroot → rootfs root. The host reads it back to forward
/// published ports to the guest. The sibling of [`EXIT_FILE`]; the kernel brings
/// the interface up via `ip=dhcp` before PID1 runs, so the address is present.
pub const IP_FILE: &str = "/.lightr-ip";

/// Host-written gate metadata. This is distinct from [`CMD_FILE`] so a snapshot
/// cannot accidentally treat command bytes as authorization to release it.
pub const SUSPEND_GATE_FILE: &str = "/.lightr-suspend-gate.json";

/// Guest-ready proof, fsynced by PID1 after mount/configuration and before any
/// workload spawn. The host waits for this before pausing a VZ VM.
pub const SUSPEND_READY_FILE: &str = "/.lightr-suspend-ready";

/// Host release proof. PID1 accepts only the exact token from gate metadata.
pub const SUSPEND_RELEASE_FILE: &str = "/.lightr-suspend-release";

/// Guest workload PID proof. Written and fsynced only after exact gate release
/// and successful child spawn; host must reject missing or malformed proof.
pub const WORKLOAD_PID_FILE: &str = "/.lightr-workload-pid";

/// The PATH injected into the guest command's environment. SINGLE SOURCE OF
/// TRUTH: the vz engine puts this in the command's env (InitSpec), and the
/// vz-memo key (lightr-cli handler) hashes the SAME value — if these drifted, a
/// memo HIT could replay a result produced under a different environment. Both
/// reference this const so they can never diverge.
pub const GUEST_PATH: &str = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";

/// Exit code reported when the command cannot be spawned (ENOENT etc.). Matches
/// the shell "command not found" convention so the host sees a real, non-zero
/// outcome rather than a fabricated success.
pub const SPAWN_FAILED_CODE: i32 = 127;

/// What PID1 must do, as data — written by the host to [`CMD_FILE`] on the
/// rootfs share, read back by the guest.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct InitSpec {
    pub command: Vec<String>,
    pub cwd: String,
    pub env: Vec<(String, String)>,
    /// When true, the guest publishes its primary IPv4 to [`IP_FILE`] before
    /// spawning the command (container networking). Default false (no-op) so the
    /// non-networked path — including the vz-memo path — is byte-identical.
    #[serde(default)]
    pub net: bool,
    /// Snapshot gate is opt-in and serializes independently in
    /// [`SUSPEND_GATE_FILE`]. A restored VM must still observe a token-matched
    /// release before it spawns the workload.
    #[serde(default)]
    pub suspend_gate: bool,
}

/// Persisted authority for one snapshot gate. Host creates this before boot;
/// guest never synthesizes it. Tokens are opaque and exact-match only.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SuspendGate {
    pub version: u8,
    pub instance_id: String,
    pub release_token: String,
}

impl SuspendGate {
    pub fn validate(&self) -> std::io::Result<()> {
        if self.version != 1 || self.instance_id.is_empty() || self.release_token.is_empty() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "invalid suspend gate metadata",
            ));
        }
        Ok(())
    }
}

impl InitSpec {
    /// Parse an `InitSpec` from canonical serde_json bytes. Roundtrip-stable
    /// with [`InitSpec::to_json`].
    pub fn from_json(b: &[u8]) -> Result<Self, String> {
        serde_json::from_slice(b).map_err(|e| e.to_string())
    }

    /// Serialize to canonical serde_json bytes. Roundtrip-stable with
    /// [`InitSpec::from_json`].
    pub fn to_json(&self) -> Vec<u8> {
        // Serializing an owned struct of String/Vec never fails; surface any
        // future failure loudly rather than fabricate empty bytes.
        serde_json::to_vec(self).expect("InitSpec serializes to JSON")
    }
}

/// Where PID1 reports the guest process exit code. Seam: tests use a Vec, the
/// real guest writes [`EXIT_FILE`] on the rootfs share.
pub trait ExitSink {
    fn report(&mut self, code: i32) -> std::io::Result<()>;
}

/// OS actions PID1 performs, seamed for host-side testing. The real impls live
/// in `bin/init.rs` (`#[cfg(target_os="linux")]`); tests use a fake.
pub trait GuestOps {
    /// Mount the rootfs virtiofs share ([`ROOTFS_TAG`]) at [`ROOTFS_DEST`].
    fn mount_rootfs(&mut self) -> std::io::Result<()>;
    /// Read + parse the command [`InitSpec`] from [`CMD_FILE`] on the mounted
    /// rootfs (i.e. `ROOTFS_DEST` + `CMD_FILE`), before chroot.
    fn read_spec(&mut self) -> std::io::Result<InitSpec>;
    /// Enter the rootfs (chroot [`ROOTFS_DEST`] + chdir `/`) so the command
    /// resolves inside the guest rootfs, not the initrd.
    fn enter_rootfs(&mut self) -> std::io::Result<()>;
    /// Spawn the command, wait, return its exit code (128+signal on signal).
    /// `pid_proof` is the released snapshot gate, present only for a
    /// `suspend_gate` run: then, after spawn and before waiting, the workload PID
    /// proof goes to [`WORKLOAD_PID_FILE`]. An ordinary run has no gate file, so
    /// it must never be asked for a proof.
    fn spawn_wait(
        &mut self,
        cmd: &[String],
        cwd: &str,
        env: &[(String, String)],
        pid_proof: Option<&SuspendGate>,
    ) -> std::io::Result<i32>;
    /// Publish the guest's primary non-loopback IPv4 to [`IP_FILE`] (container
    /// networking). Called by [`run_init`] only when [`InitSpec::net`] is true,
    /// AFTER `enter_rootfs` (so the file lands on the rootfs share) and BEFORE
    /// `spawn_wait` (the command may block forever as a server).
    fn publish_ip(&mut self) -> std::io::Result<()>;
    /// Fsync a guest-ready proof, then wait for the host's exact release token.
    /// This must complete before `spawn_wait` is invoked. Returns the validated
    /// gate, which `spawn_wait` uses for the workload PID proof.
    fn await_suspend_release(&mut self) -> std::io::Result<SuspendGate>;
}

/// The init lifecycle: mount rootfs → read the command → enter the rootfs →
/// spawn → report the exit code. Fixed order.
///
/// Honesty invariant (the whole point of this WP): `sink.report()` is called
/// with the ACTUAL exit code — never a hardcoded success.
/// - A mount or spec-read failure propagates as `Err` and reports NOTHING (no
///   fake code — the host then maps the missing exit file to a real non-zero).
/// - A spawn failure (e.g. ENOENT) is a real outcome: report
///   [`SPAWN_FAILED_CODE`] (127) and return it.
pub fn run_init<M: GuestOps>(ops: &mut M, sink: &mut dyn ExitSink) -> std::io::Result<i32> {
    // 1. Mount the rootfs share. A mount failure is unrecoverable → propagate,
    //    report NOTHING.
    ops.mount_rootfs()?;

    // 2. Read the command the host placed on the share. A missing/garbled spec
    //    is also unrecoverable → propagate, report NOTHING.
    let spec = ops.read_spec()?;

    // 3. Enter the rootfs so the command resolves there (not the initrd).
    ops.enter_rootfs()?;

    // 3b. Container networking: publish the guest IP BEFORE spawn (a published
    //     server blocks forever, so this must precede the spawn). Gated on net.
    if spec.net {
        ops.publish_ip()?;
    }

    // Snapshot protocol: readiness is durable before VZ pauses, while release is
    // impossible until host validates/restores exact artifact after first payload.
    let gate = if spec.suspend_gate {
        Some(ops.await_suspend_release()?)
    } else {
        None
    };

    // 4. Spawn and capture the REAL exit code. A spawn failure (command not
    //    found) is still a real outcome → 127, not an Err. Only a gated run
    //    writes the workload PID proof (ADR-0024 D6: reading the gate file on
    //    every run made each ordinary run report 127).
    let code = match ops.spawn_wait(&spec.command, &spec.cwd, &spec.env, gate.as_ref()) {
        Ok(code) => code,
        Err(_) => SPAWN_FAILED_CODE,
    };

    // 5. Report the actual code, then return it. This is the line that kills the
    //    vz shim's old hardcoded exitCode=0.
    sink.report(code)?;
    Ok(code)
}

#[cfg(test)]
mod tests;

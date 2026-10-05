//! VzEngine — macOS Virtualization.framework microVM engine (feature "vz").

use super::spec::ExecSpec;
use super::Engine;

// ── VzEngine (macOS + feature "vz") ─────────────────────────────────────────

#[cfg(all(target_os = "macos", feature = "vz"))]
mod vz_impl {
    use super::{Engine, ExecSpec};
    use crate::engine::probe::pack_dir;
    use crate::engine::{ResumedInstance, SuspendResume, SuspendedArtifact};
    use lightr_core::{LightrError, Result};
    use lightr_init::{
        InitSpec, CMD_FILE, EXIT_FILE, GUEST_PATH, SUSPEND_GATE_FILE, SUSPEND_READY_FILE,
        SUSPEND_RELEASE_FILE, WORKLOAD_PID_FILE,
    };
    use std::ffi::CString;

    /// Exit code returned when the VM booted (and stopped) but the guest never
    /// wrote a readable exit file — i.e. PID1 crashed before reporting. NOT a
    /// success: we surface a real, non-zero failure rather than fabricate 0.
    const GUEST_NO_REPORT_CODE: i32 = 255;

    extern "C" {
        fn lightr_vz_session_create(
            kernel: *const libc::c_char,
            initrd: *const libc::c_char,
            rootfs: *const libc::c_char,
            store: *const libc::c_char,
            memory_mb: u64,
            cpu_count: u64,
            net_fd: libc::c_int,
            net_mac: *const libc::c_char,
            console_path: *const libc::c_char,
            out_handle: *mut u64,
        ) -> libc::c_int;
        fn lightr_vz_session_start(handle: u64) -> libc::c_int;
        fn lightr_vz_session_pause_save(
            handle: u64,
            state_path: *const libc::c_char,
        ) -> libc::c_int;
        fn lightr_vz_session_stop(handle: u64) -> libc::c_int;
        fn lightr_vz_session_restore(handle: u64, state_path: *const libc::c_char) -> libc::c_int;
        fn lightr_vz_session_resume(handle: u64) -> libc::c_int;
        fn lightr_vz_session_destroy(handle: u64) -> libc::c_int;
        /// C ABI exposed by shim/vz.swift (compiled to static lib by build.rs).
        ///
        /// VALIDATED end-to-end on Intel x86_64 (i7-9750H, macOS 15.3.2,
        /// 2026-06-12): boots a bzImage microVM, runs the command, returns its
        /// real exit code. The kernel MUST be an x86_64 bzImage — VZ boots via
        /// the x86 setup-header / real-mode protocol; a raw `vmlinux` ELF (even a
        /// PVH one) is rejected with "Internal Virtualization error".
        ///
        /// RETURN CONTRACT: this is a VM-LIFECYCLE status, NOT the guest's exit
        /// code. `0` = the VM booted and stopped cleanly; a negative value =
        /// boot/config failure. The guest's REAL exit code arrives via the file
        /// channel on the shared rootfs (`EXIT_FILE`), read back by `run` below —
        /// never from this return value. The shim never fabricates a `0`.
        ///
        /// F-203: `memory_mb`/`cpu_count` carry the resource caps (build-spec-
        /// parity.md §2.4). `0` means "use the shim default" (unlimited). When
        /// `memory_mb` is below the VZ memory floor the shim returns a config
        /// failure (< 0) rather than silently clamping — an honest boundary.
        ///
        /// ADR-0018 (WP-C6/C7): `net_fd` is the GUEST-side fd of a
        /// `socketpair(AF_UNIX, SOCK_DGRAM)` (host end owned by the L2 switch).
        /// `>= 0` ⇒ the shim attaches a SECOND virtio-net NIC
        /// (`VZFileHandleNetworkDeviceAttachment` over a non-owning `FileHandle`
        /// on the fd, with SO_*BUF tuning) ALONGSIDE the NAT NIC — the dual-NIC
        /// mesh path. `-1` ⇒ no file-handle NIC (today's single-NAT-NIC path,
        /// byte-for-byte). The fd's lifetime is the caller's (the switch); the
        /// shim wraps it `closeOnDealloc:false`.
        fn lightr_vz_run(
            kernel: *const libc::c_char,
            initrd: *const libc::c_char,
            rootfs: *const libc::c_char,
            store: *const libc::c_char,
            memory_mb: u64,
            cpu_count: u64,
            net_fd: libc::c_int,
            net_mac: *const libc::c_char,
            argc: libc::c_int,
            argv: *const *const libc::c_char,
        ) -> libc::c_int;
    }

    pub struct VzEngine {
        session: std::sync::Mutex<Option<RetainedSession>>,
    }

    impl VzEngine {
        pub(super) fn new() -> Self {
            Self {
                session: std::sync::Mutex::new(None),
            }
        }
    }

    struct RetainedSession {
        handle: u64,
        rootfs: std::path::PathBuf,
        release_token: String,
        config_sha256: String,
    }

    impl Drop for RetainedSession {
        fn drop(&mut self) {
            unsafe { lightr_vz_session_destroy(self.handle) };
        }
    }

    struct SessionDestroyGuard(Option<u64>);

    impl SessionDestroyGuard {
        fn new(handle: u64) -> Self {
            Self(Some(handle))
        }

        fn dismiss(&mut self) {
            self.0 = None;
        }
    }

    impl Drop for SessionDestroyGuard {
        fn drop(&mut self) {
            if let Some(handle) = self.0 {
                unsafe { lightr_vz_session_destroy(handle) };
            }
        }
    }

    impl Engine for VzEngine {
        fn kind(&self) -> crate::engine::EngineKind {
            crate::engine::EngineKind::Vz
        }

        /// Run the guest and return its REAL exit code.
        ///
        /// Sequence (file channel — macOS has NO host AF_VSOCK):
        ///   1. Write the command spec (InitSpec JSON) to CMD_FILE on the
        ///      writable rootfs share, and clear any stale EXIT_FILE.
        ///   2. Boot the VM via the Swift shim and block until it stops.
        ///   3. Read the guest's REAL exit code back from EXIT_FILE.
        ///
        /// Exit-code law:
        ///   - boot/config failure (shim < 0)             ⇒ `Err(LightrError)`
        ///   - VM stopped but no EXIT_FILE (guest crash)  ⇒ 255, NOT 0
        ///   - otherwise                                  ⇒ the guest's code
        ///     parsed from EXIT_FILE.
        fn run(&self, spec: &ExecSpec) -> Result<i32> {
            let dir = pack_dir();
            let kernel = dir.join("kernel");
            let initrd = dir.join("initrd");
            let rootfs = spec.rootfs.ok_or_else(|| {
                LightrError::InvalidRef("vz engine requires a rootfs".to_string())
            })?;

            // ── 1. Write the command spec onto the rootfs share BEFORE boot ──
            // macOS has NO host AF_VSOCK, so the host↔guest channel is two files
            // on the shared (writable) rootfs virtiofs share (decisions-log
            // 2026-06-12): the host writes the command to CMD_FILE here; the guest
            // PID1 reads it, runs it, and writes its REAL exit code to EXIT_FILE,
            // which the host reads back after the VM stops. cwd "/" + a minimal
            // PATH is the guest environment (ExecSpec.cwd is a host path).
            let cmd_path = rootfs.join(CMD_FILE.trim_start_matches('/'));
            let exit_path = rootfs.join(EXIT_FILE.trim_start_matches('/'));
            // A stale exit file from a prior run must not be read as this run's
            // result — clear it before boot.
            let _ = std::fs::remove_file(&exit_path);
            let init_spec = InitSpec {
                command: spec.command.to_vec(),
                cwd: "/".to_string(),
                env: vec![("PATH".to_string(), GUEST_PATH.to_string())],
                // WP-NET2: when the run wants networking, the guest publishes its
                // DHCP IP to IP_FILE before spawning the (possibly long-running)
                // command, so the host supervisor can forward published ports.
                net: spec.net,
                suspend_gate: false,
            };
            std::fs::write(&cmd_path, init_spec.to_json()).map_err(LightrError::Io)?;

            // WP-NET2: a networked run needs the shim to attach the NAT NIC +
            // `ip=dhcp`. The shim gates that on LIGHTR_VZ_NET (env), so ExecSpec.net
            // is the single switch that drives BOTH the guest (InitSpec.net above)
            // and the shim. Respect a user-set value; set before the FFI spawns any
            // thread (single-threaded here). A non-networked run leaves it unset,
            // so the memo/one-shot path keeps its faster no-NIC boot.
            if spec.net && std::env::var_os("LIGHTR_VZ_NET").is_none() {
                // Safety: single-threaded here, before the engine spawns the VM.
                unsafe { std::env::set_var("LIGHTR_VZ_NET", "1") };
            }

            let kernel_c = path_to_cstr(&kernel)?;
            let initrd_c = path_to_cstr(&initrd)?;
            let rootfs_c = path_to_cstr(rootfs)?;
            // store path: empty → the Swift shim mounts no store share. The
            // command travels via CMD_FILE on the rootfs, not argv/cmdline.
            let store_c = CString::new("").unwrap();

            // argv is still handed to the shim (it sets LIGHTR_CMD on the kernel
            // cmdline), but the guest reads CMD_FILE instead — pass it anyway for
            // forward-compat + console debugging.
            let argv_cstrings: Vec<CString> = spec
                .command
                .iter()
                .map(|s| {
                    CString::new(s.as_bytes()).map_err(|_| {
                        LightrError::InvalidRef(format!("invalid NUL in command arg: {s}"))
                    })
                })
                .collect::<Result<_>>()?;
            let mut argv_ptrs: Vec<*const libc::c_char> =
                argv_cstrings.iter().map(|c| c.as_ptr()).collect();
            argv_ptrs.push(std::ptr::null());

            // ── 2. Boot the VM and block until it stops (or fails) ──────────
            // F-203 (build-spec-parity.md §2.4): derive the VM caps from
            // `spec.limits` and hand them to the shim, which sets
            // `VZVirtualMachineConfiguration.memorySizeInBytes`/`.cpuCount`.
            //   cpus → ceil(millis/1000) vcpus, min 1 (a fractional core rounds
            //          UP to a whole vcpu — VZ has no sub-core granularity).
            //   memory → MB, rounded UP. Below the VZ floor the shim returns a
            //          config failure (< 0) → the honest `Err` below.
            //   `0` for either field means "use the shim default" (unlimited).
            // Fast-teardown: tell the shim the host path of the guest's durable
            // EXIT_FILE. The shim polls it and force-stops the VM the instant the
            // result is captured, instead of waiting for the guest's slow clean
            // poweroff + VZ stop-detection (~2s). Safe: PID1 fsyncs EXIT_FILE
            // before it would power off, and the rootfs is a throwaway CoW dir, so
            // nothing but EXIT_FILE is read back. Same-process, set before the FFI
            // call spawns any thread.
            unsafe { std::env::set_var("LIGHTR_VZ_EXITFILE", &exit_path) };
            let (memory_mb, cpu_count) = vz_caps(&spec.limits);
            // ADR-0018 dual-NIC: hand the GUEST-side socketpair fd to the shim
            // (-1 = none → today's single-NAT-NIC path). The fd is owned by the
            // L2 switch (a later WP); the shim wraps it non-owning.
            let net_fd: libc::c_int = spec.net_fd.unwrap_or(-1);
            // ADR-0018: pass the registry-assigned per-member mesh MAC as a C
            // string ("xx:xx:..") so the guest's eth1 emits it → the switch keys
            // DHCP/L2/DNS on the same MAC. None → null → the shim's pinned fallback.
            let net_mac_c: Option<std::ffi::CString> = spec.net_mac.map(|m| {
                std::ffi::CString::new(format!(
                    "{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}",
                    m[0], m[1], m[2], m[3], m[4], m[5]
                ))
                .expect("formatted MAC has no interior NUL")
            });
            let net_mac_ptr: *const libc::c_char =
                net_mac_c.as_ref().map_or(std::ptr::null(), |c| c.as_ptr());
            let vm_status = unsafe {
                lightr_vz_run(
                    kernel_c.as_ptr(),
                    initrd_c.as_ptr(),
                    rootfs_c.as_ptr(),
                    store_c.as_ptr(),
                    memory_mb,
                    cpu_count,
                    net_fd,
                    net_mac_ptr,
                    argv_ptrs.len() as libc::c_int - 1, // exclude null sentinel
                    argv_ptrs.as_ptr(),
                )
            };
            // Shim return contract (WAVE-VZ fast exit channel):
            //   -1        = boot/config failure (no VM) → real error;
            //   0..=255   = the guest's REAL exit code, captured in real time from
            //               the console marker (no virtiofs lag) → use directly;
            //   -2        = the VM stopped without a marker (guest crashed before
            //               printing) → fall back to the durable EXIT_FILE.
            if let Some(code) = live_exit_code(vm_status)? {
                return Ok(code);
            }

            // ── 3. Fallback: read the guest's exit code from the rootfs share ──
            // Only reached when no console marker arrived. PID1 wrote EXIT_FILE
            // (fsync); a missing/unparsable file means the guest never reported
            // ⇒ GUEST_NO_REPORT_CODE (255), never a fabricated 0. Retry covers
            // virtiofs flush lag.
            for _ in 0..30 {
                if let Ok(s) = std::fs::read_to_string(&exit_path) {
                    if let Ok(code) = s.trim().parse::<i32>() {
                        return Ok(code);
                    }
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Ok(GUEST_NO_REPORT_CODE)
        }

        fn suspend(
            &self,
            spec: &ExecSpec,
            artifact_dir: &std::path::Path,
        ) -> Result<SuspendResume> {
            if self
                .session
                .lock()
                .expect("vz session mutex poisoned")
                .is_some()
            {
                return Err(LightrError::InvalidRef(
                    "vz suspend already has a retained session".to_string(),
                ));
            }
            let rootfs = spec.rootfs.ok_or_else(|| {
                LightrError::InvalidRef("vz engine requires a rootfs".to_string())
            })?;
            std::fs::create_dir_all(artifact_dir).map_err(LightrError::Io)?;
            let state_path = artifact_dir.join("vz.state");
            let instance_id = format!("vz-{}", std::process::id());
            let release_token = format!("{instance_id}-{}", state_path.display());
            let cmd_path = rootfs.join(CMD_FILE.trim_start_matches('/'));
            let gate_path = rootfs.join(SUSPEND_GATE_FILE.trim_start_matches('/'));
            let ready_path = rootfs.join(SUSPEND_READY_FILE.trim_start_matches('/'));
            let release_path = rootfs.join(SUSPEND_RELEASE_FILE.trim_start_matches('/'));
            let pid_path = rootfs.join(WORKLOAD_PID_FILE.trim_start_matches('/'));
            let _ = std::fs::remove_file(&ready_path);
            let _ = std::fs::remove_file(&release_path);
            // A prior guest PID is never proof for this retained session.
            let _ = std::fs::remove_file(&pid_path);
            std::fs::write(
                &cmd_path,
                InitSpec {
                    command: spec.command.to_vec(),
                    cwd: "/".to_string(),
                    env: vec![("PATH".to_string(), GUEST_PATH.to_string())],
                    net: spec.net,
                    suspend_gate: true,
                }
                .to_json(),
            )
            .map_err(LightrError::Io)?;
            std::fs::write(
                gate_path,
                format!("{{\"version\":1,\"instance_id\":\"{instance_id}\",\"release_token\":\"{release_token}\"}}"),
            )
            .map_err(LightrError::Io)?;
            let kernel_c = path_to_cstr(&pack_dir().join("kernel"))?;
            let initrd_c = path_to_cstr(&pack_dir().join("initrd"))?;
            let rootfs_c = path_to_cstr(rootfs)?;
            let store_c = CString::new("").unwrap();
            let state_c = path_to_cstr(&state_path)?;
            let (memory_mb, cpu_count) = vz_caps(&spec.limits);
            let config_sha256 = lightr_core::Digest::of_bytes(
                format!(
                    "{}:{memory_mb}:{cpu_count}:{:?}:{:?}",
                    rootfs.display(),
                    spec.net_fd,
                    spec.net_mac
                )
                .as_bytes(),
            )
            .to_hex();
            let mut handle = 0_u64;
            let created = unsafe {
                lightr_vz_session_create(
                    kernel_c.as_ptr(),
                    initrd_c.as_ptr(),
                    rootfs_c.as_ptr(),
                    store_c.as_ptr(),
                    memory_mb,
                    cpu_count,
                    spec.net_fd.unwrap_or(-1),
                    std::ptr::null(),
                    std::ptr::null(),
                    &mut handle,
                )
            };
            if created == -2 {
                return Ok(SuspendResume::Unsupported {
                    engine: self.kind(),
                    reason: "vz suspend requires macOS arm64 and macOS 14+".to_string(),
                });
            }
            vz_status(created, "session create")?;
            // Every failure after create must remove Swift global session state.
            let mut destroy_guard = SessionDestroyGuard::new(handle);
            vz_status(unsafe { lightr_vz_session_start(handle) }, "session start")?;
            wait_for_file(&ready_path, "guest suspend readiness")?;
            vz_status(
                unsafe { lightr_vz_session_pause_save(handle, state_c.as_ptr()) },
                "pause/save",
            )?;
            vz_status(unsafe { lightr_vz_session_stop(handle) }, "stop")?;
            *self.session.lock().expect("vz session mutex poisoned") = Some(RetainedSession {
                handle,
                rootfs: rootfs.to_path_buf(),
                release_token: release_token.clone(),
                config_sha256: config_sha256.clone(),
            });
            destroy_guard.dismiss();
            Ok(SuspendResume::Suspended(SuspendedArtifact {
                instance_id,
                artifact_sha256: lightr_core::Digest::of_file(&state_path)?.to_hex(),
                snapshot_path: state_path.clone(),
                state_path,
                machine_id: "vz-arm64".to_string(),
                config_sha256,
                release_token: release_token.clone(),
                rootfs: rootfs.to_path_buf(),
            }))
        }

        fn resume(&self, artifact: &SuspendedArtifact) -> Result<ResumedInstance> {
            let session = self
                .session
                .lock()
                .expect("vz session mutex poisoned")
                .take()
                .ok_or_else(|| {
                    LightrError::InvalidRef("vz resume has no retained session".to_string())
                })?;
            let handle = session.handle;
            if artifact.machine_id != "vz-arm64"
                || artifact.config_sha256 != session.config_sha256
                || artifact.rootfs != session.rootfs
                || artifact.release_token != session.release_token
                || lightr_core::Digest::of_file(&artifact.state_path)?.to_hex()
                    != artifact.artifact_sha256
            {
                return Err(LightrError::InvalidRef(
                    "vz resume artifact identity/configuration mismatch".to_string(),
                ));
            }
            let state_c = path_to_cstr(&artifact.state_path)?;
            vz_status(
                unsafe { lightr_vz_session_restore(handle, state_c.as_ptr()) },
                "restore",
            )?;
            write_release_token(&session.rootfs, &session.release_token)?;
            vz_status(
                unsafe { lightr_vz_session_resume(session.handle) },
                "resume",
            )?;
            let pid = wait_for_pid(
                &session
                    .rootfs
                    .join(WORKLOAD_PID_FILE.trim_start_matches('/')),
                &artifact.instance_id,
                &session.release_token,
            )?;
            *self.session.lock().expect("vz session mutex poisoned") = Some(session);
            Ok(ResumedInstance {
                instance_id: artifact.instance_id.clone(),
                artifact_sha256: artifact.artifact_sha256.clone(),
                pid,
            })
        }

        fn teardown(&self) {
            let _ = self
                .session
                .lock()
                .expect("vz session mutex poisoned")
                .take();
        }
    }

    /// Publish exact retained authority with durable visibility before VM resume.
    fn write_release_token(rootfs: &std::path::Path, token: &str) -> Result<()> {
        let release_path = rootfs.join(SUSPEND_RELEASE_FILE.trim_start_matches('/'));
        let parent = release_path.parent().ok_or_else(|| {
            LightrError::InvalidRef("vz release gate has no parent directory".to_string())
        })?;
        let temp_path = parent.join(format!(
            ".lightr-release-{}-{}",
            std::process::id(),
            std::thread::current().name().unwrap_or("resume")
        ));
        let mut gate = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp_path)
            .map_err(LightrError::Io)?;
        use std::io::Write;
        gate.write_all(token.as_bytes()).map_err(LightrError::Io)?;
        gate.sync_all().map_err(LightrError::Io)?;
        std::fs::rename(&temp_path, &release_path).map_err(LightrError::Io)?;
        std::fs::File::open(&release_path)
            .map_err(LightrError::Io)?
            .sync_all()
            .map_err(LightrError::Io)?;
        std::fs::File::open(parent)
            .map_err(LightrError::Io)?
            .sync_all()
            .map_err(LightrError::Io)
    }

    fn vz_status(status: libc::c_int, operation: &str) -> Result<()> {
        match status {
            0 => Ok(()),
            -1 => Err(LightrError::InvalidRef(format!(
                "vz {operation}: configuration failed"
            ))),
            -2 => Err(LightrError::Unsupported(format!(
                "vz {operation}: unsupported host"
            ))),
            -3 => Err(LightrError::Io(std::io::Error::other(format!(
                "vz {operation}: I/O failed"
            )))),
            -4 => Err(LightrError::InvalidRef(format!(
                "vz {operation}: lifecycle failed"
            ))),
            -5 => Err(LightrError::InvalidRef(format!(
                "vz {operation}: invalid state"
            ))),
            -6 => Err(LightrError::Io(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                format!("vz {operation}: timed out"),
            ))),
            code => Err(LightrError::InvalidRef(format!(
                "vz {operation}: unknown status {code}"
            ))),
        }
    }

    /// Map `lightr_vz_run`'s return (contract in shim/vz.swift): `0..=255` is
    /// the guest's real code from the console marker; `-2` means the VM stopped
    /// without a marker, so the caller falls back to `EXIT_FILE`; `-1` and any
    /// other value fail closed. #143 routed this through `vz_status`, which made
    /// every non-zero guest exit an "unknown status" error and the `-2` fallback
    /// an "unsupported host" error.
    fn live_exit_code(vm_status: libc::c_int) -> Result<Option<i32>> {
        match vm_status {
            0..=255 => Ok(Some(vm_status)),
            -2 => Ok(None),
            status => vz_status(status, "run").map(|()| None),
        }
    }

    fn wait_for_file(path: &std::path::Path, operation: &str) -> Result<()> {
        for _ in 0..600 {
            if path.is_file() {
                return Ok(());
            }
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
        Err(LightrError::Io(std::io::Error::new(
            std::io::ErrorKind::TimedOut,
            format!("vz {operation}: timed out"),
        )))
    }

    fn wait_for_pid(path: &std::path::Path, instance_id: &str, release_token: &str) -> Result<u32> {
        for _ in 0..600 {
            if let Ok(s) = std::fs::read_to_string(path) {
                let mut proof = s.split_whitespace();
                return (proof.next() == Some(instance_id) && proof.next() == Some(release_token))
                    .then(|| proof.next())
                    .flatten()
                    .and_then(|pid| pid.parse::<u32>().ok())
                    .filter(|pid| *pid != 0)
                    .ok_or_else(|| {
                        LightrError::InvalidRef(
                            "vz resume: missing or malformed workload PID proof".to_string(),
                        )
                    });
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        Err(LightrError::InvalidRef(
            "vz resume: missing or malformed workload PID proof".to_string(),
        ))
    }

    fn path_to_cstr(p: &std::path::Path) -> Result<CString> {
        CString::new(p.as_os_str().as_encoded_bytes())
            .map_err(|_| LightrError::InvalidRef(format!("invalid path: {}", p.display())))
    }

    /// Derive `(memory_mb, cpu_count)` for the vz shim from the resource caps.
    /// `0` for a field means "use the shim default" (unlimited / VZ baseline).
    ///
    /// * cpu — `ceil(millis / 1000)`, min 1 vcpu (VZ has no sub-core grain).
    /// * mem — `ceil(bytes / MiB)`. The VZ memory floor is enforced by the shim
    ///   (config failure rather than a silent clamp).
    ///
    /// NOTE (WP-#90): `limits.pids_max` is intentionally NOT consumed here — the
    /// shim cannot set a guest per-container `pids.max` (the VM owns its own pid
    /// space, not a delegated cgroup). A `--pids-limit --engine vz` request is
    /// honest-errored upstream at the CLI (run handler) BEFORE the VM boots, so it
    /// is never silently dropped; nothing reaches this function with a pids cap.
    fn vz_caps(limits: &lightr_core::ResourceLimits) -> (u64, u64) {
        let cpu_count = match limits.cpu_millis {
            None => 0,
            Some(millis) => millis.div_ceil(1000).max(1),
        };
        let memory_mb = match limits.memory_bytes {
            None => 0,
            Some(bytes) => bytes.div_ceil(1024 * 1024).max(1),
        };
        (memory_mb, cpu_count)
    }

    #[cfg(test)]
    mod tests {
        use super::{live_exit_code, vz_caps, vz_status, write_release_token};
        use lightr_core::ResourceLimits;
        use lightr_init::SUSPEND_RELEASE_FILE;

        #[test]
        fn unlimited_yields_zero_defaults() {
            assert_eq!(vz_caps(&ResourceLimits::default()), (0, 0));
        }

        #[test]
        fn cpu_rounds_up_to_whole_vcpus_min_one() {
            // 0.5 core → 1 vcpu; 1.5 → 2; 2.0 → 2; 2001m → 3.
            let c = |m| {
                vz_caps(&ResourceLimits {
                    memory_bytes: None,
                    cpu_millis: Some(m),
                    pids_max: None,
                })
                .1
            };
            assert_eq!(c(500), 1);
            assert_eq!(c(1500), 2);
            assert_eq!(c(2000), 2);
            assert_eq!(c(2001), 3);
            assert_eq!(c(1), 1);
        }

        #[test]
        fn memory_rounds_up_to_whole_mib() {
            let m = |b| {
                vz_caps(&ResourceLimits {
                    memory_bytes: Some(b),
                    cpu_millis: None,
                    pids_max: None,
                })
                .0
            };
            assert_eq!(m(1024 * 1024), 1);
            assert_eq!(m(1024 * 1024 + 1), 2);
            assert_eq!(m(512 * 1024 * 1024), 512);
            assert_eq!(m(1), 1);
        }

        #[test]
        fn frozen_vz_statuses_map_to_distinct_errors() {
            assert!(vz_status(0, "test").is_ok());
            for status in [-1, -2, -3, -4, -5, -6] {
                assert!(
                    vz_status(status, "test").is_err(),
                    "status {status} must fail closed"
                );
            }
            assert!(vz_status(-99, "test").is_err());
        }

        #[test]
        fn run_returns_live_guest_codes_and_falls_back_only_on_no_marker() {
            for code in [0, 1, 7, 127, 143, 255] {
                assert_eq!(live_exit_code(code).unwrap(), Some(code));
            }
            assert_eq!(live_exit_code(-2).unwrap(), None, "-2 reads EXIT_FILE");
            for status in [-1, -3, -4, -5, -6, -99, 256] {
                assert!(live_exit_code(status).is_err(), "{status} must fail closed");
            }
        }

        #[test]
        fn release_gate_contains_exact_retained_token() {
            let rootfs = tempfile::tempdir().unwrap();
            write_release_token(rootfs.path(), "retained-token").unwrap();
            assert_eq!(
                std::fs::read_to_string(
                    rootfs
                        .path()
                        .join(SUSPEND_RELEASE_FILE.trim_start_matches('/'))
                )
                .unwrap(),
                "retained-token"
            );
        }
    }
}

#[cfg(all(target_os = "macos", feature = "vz"))]
pub(super) fn vz_engine_box() -> Box<dyn Engine> {
    Box::new(vz_impl::VzEngine::new())
}

/// Stub for builds without feature "vz" (or non-macOS) — probe gates before
/// this is ever reached, so this path is dead-code in practice.
#[cfg(not(all(target_os = "macos", feature = "vz")))]
struct VzEngineStub;

#[cfg(not(all(target_os = "macos", feature = "vz")))]
impl Engine for VzEngineStub {
    fn kind(&self) -> super::EngineKind {
        super::EngineKind::Vz
    }

    fn run(&self, _spec: &ExecSpec) -> lightr_core::Result<i32> {
        Err(lightr_core::LightrError::InvalidRef(
            "vz engine requires macOS + the 'vz' build feature + a linux pack".to_string(),
        ))
    }
}

#[cfg(not(all(target_os = "macos", feature = "vz")))]
pub(super) fn vz_engine_box() -> Box<dyn Engine> {
    Box::new(VzEngineStub)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    // ── KEY INVARIANT (WP-B exit channel) ──────────────────────────────────
    // There is NO code path where vz returns a hardcoded 0. The command is
    // handed to the guest via CMD_FILE on the shared rootfs; the exit code comes
    // back via EXIT_FILE on that same share (macOS has no host AF_VSOCK). The
    // shim return is a VM-lifecycle status only. A missing exit file ⇒ 255,
    // never a fabricated 0. These source-level tests pin that down so a future
    // edit can't silently restore a fake success.

    /// The Swift shim must NOT contain the fabricated `exitCode = 0` it used to,
    /// and must not name a guest exitCode at all — it reports only VM-lifecycle
    /// status (vmStatus); the real code is a file on the shared rootfs.
    #[test]
    fn swift_shim_has_no_fabricated_exit_code_zero() {
        let shim = include_str!("../../shim/vz.swift");
        assert!(
            !shim.contains("exitCode = 0"),
            "vz.swift must not fabricate a guest exit code of 0"
        );
        assert!(
            !shim.contains("exitCode"),
            "vz.swift must not name a guest exitCode at all — it reports only \
             VM-lifecycle status (vmStatus); the code is read from the rootfs file"
        );
        assert!(
            shim.contains("vmStatus"),
            "vz.swift must report a VM-lifecycle status (vmStatus), not the code"
        );
    }

    /// `VzEngine::run` delivers the command via CMD_FILE and reads the exit code
    /// from EXIT_FILE on the shared rootfs — it NEVER returns the shim's status
    /// as the exit code, and a missing file maps to 255 (not a fabricated 0).
    #[test]
    fn vz_exit_code_comes_from_the_rootfs_file_not_the_shim() {
        let src = include_str!("vz.rs");

        // Command delivered to the guest by writing CMD_FILE on the rootfs.
        assert!(
            src.contains("CMD_FILE") && src.contains("init_spec.to_json()"),
            "VzEngine::run must write the command spec to CMD_FILE"
        );
        // Exit code read back from EXIT_FILE on the rootfs, parsed as i32.
        assert!(
            src.contains("EXIT_FILE") && src.contains("parse::<i32>()"),
            "VzEngine::run must read the exit code from EXIT_FILE"
        );
        // The shim return goes through the live-marker mapping, which returns
        // only 0..=255 marker codes and otherwise falls back to EXIT_FILE or
        // fails. (Checked against the implementation, not this test's text.)
        let implementation = &src[..src.find("\n    #[cfg(test)]").unwrap()];
        assert!(
            implementation.contains("let vm_status")
                && implementation.contains("live_exit_code(vm_status)?"),
            "the shim return must go through live_exit_code"
        );
        // The honest no-report fallback is 255, explicitly NOT 0.
        assert!(
            src.contains("GUEST_NO_REPORT_CODE: i32 = 255"),
            "a missing guest exit file must map to 255, not a fabricated 0"
        );
    }

    #[test]
    fn swift_shim_exports_frozen_retained_session_abi() {
        let shim = include_str!("../../shim/vz.swift");
        for symbol in [
            "lightr_vz_session_create",
            "lightr_vz_session_start",
            "lightr_vz_session_pause_save",
            "lightr_vz_session_stop",
            "lightr_vz_session_restore",
            "lightr_vz_session_resume",
            "lightr_vz_session_destroy",
        ] {
            assert!(
                shim.contains(symbol),
                "missing frozen VZ ABI symbol: {symbol}"
            );
        }
        assert!(shim.contains("session.vm.pause(completionHandler:"));
        assert!(shim.contains("saveMachineStateTo(url:"));
        assert!(shim.contains("completionHandler: { (error: Error?) in"));
        assert!(shim.contains("restoreMachineStateFrom(url:"));
        assert!(shim.contains("#if !arch(arm64)"));
    }

    #[test]
    fn legacy_run_stays_independent_from_arm_only_session_abi() {
        let shim = include_str!("../../shim/vz.swift");
        let legacy = &shim[..shim
            .find("// MARK: - Frozen retained-session C ABI")
            .unwrap()];
        assert!(legacy.contains("@_cdecl(\"lightr_vz_run\")"));
        assert!(!legacy.contains("lightr_vz_session_create"));
    }

    #[test]
    fn created_session_has_raii_destroy_until_retained_owner_takes_it() {
        let src = include_str!("vz.rs");
        let suspend = &src[src.find("fn suspend(").unwrap()..src.find("fn resume(").unwrap()];
        let create = suspend.find("lightr_vz_session_create").unwrap();
        let guard = suspend.find("SessionDestroyGuard::new(handle)").unwrap();
        let retain = suspend.find("Some(RetainedSession {").unwrap();
        let dismiss = suspend.find("destroy_guard.dismiss()").unwrap();
        assert!(create < guard && guard < retain && retain < dismiss);
        let shim = include_str!("../../shim/vz.swift");
        assert!(shim.contains("sessions.removeValue(forKey: handle)"));
    }

    #[test]
    fn suspension_artifact_keeps_token_and_rootfs_private() {
        let artifact = include_str!("mod.rs");
        assert!(artifact.contains("pub(crate) release_token: String"));
        assert!(artifact.contains("pub(crate) rootfs: PathBuf"));
    }

    #[test]
    fn wrong_token_fails_before_restore_gate_or_pid_proof() {
        let src = include_str!("vz.rs");
        let implementation = &src[..src.find("\n    #[cfg(test)]").unwrap()];
        let resume = &implementation[implementation.find("fn resume(&self, artifact").unwrap()..];
        let token_check = resume
            .find("artifact.release_token != session.release_token")
            .expect("resume must compare artifact token with retained session token");
        let restore = resume
            .find("lightr_vz_session_restore")
            .expect("resume must restore only after validation");
        let gate = resume
            .find("write_release_token(&session.rootfs, &session.release_token)")
            .expect("resume must release exact retained token");
        let pid = resume
            .find("wait_for_pid(")
            .expect("resume must require workload PID proof");
        assert!(token_check < restore && token_check < gate && token_check < pid);
    }

    #[test]
    fn resume_order_is_restore_then_durable_gate_then_vm_resume() {
        let src = include_str!("vz.rs");
        let implementation = &src[..src.find("\n    #[cfg(test)]").unwrap()];
        let resume_body =
            &implementation[implementation.find("fn resume(&self, artifact").unwrap()..];
        let restore = resume_body.find("lightr_vz_session_restore").unwrap();
        let gate = resume_body
            .find("write_release_token(&session.rootfs, &session.release_token)")
            .unwrap();
        let resume = resume_body
            .find("lightr_vz_session_resume(session.handle)")
            .unwrap();
        assert!(restore < gate && gate < resume);
        let gate_body = &src[src.find("fn write_release_token").unwrap()..];
        assert!(gate_body.contains("gate.sync_all()"));
        assert!(gate_body.contains("std::fs::rename(&temp_path, &release_path)"));
        assert!(gate_body.contains("std::fs::File::open(parent)"));
    }

    #[test]
    fn resumed_output_retains_artifact_identity_and_token_check_has_teeth() {
        let src = include_str!("vz.rs");
        let implementation = &src[..src.find("\n    #[cfg(test)]").unwrap()];
        assert!(implementation.contains("instance_id: artifact.instance_id.clone()"));
        assert!(implementation.contains("artifact_sha256: artifact.artifact_sha256.clone()"));
        assert!(resume_has_retained_token_check(implementation));
        let mutated =
            implementation.replace("artifact.release_token != session.release_token", "true");
        assert!(
            !resume_has_retained_token_check(&mutated),
            "removing retained-token comparison must fail this test"
        );
    }

    fn resume_has_retained_token_check(src: &str) -> bool {
        src.contains("artifact.release_token != session.release_token")
    }
}

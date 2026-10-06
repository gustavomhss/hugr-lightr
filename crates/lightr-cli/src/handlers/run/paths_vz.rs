//! The vz-memo path helper (`run_vz_memo`), extracted verbatim from `paths.rs`
//! to keep that file under the 400-line godfile cap.

use std::io::Write;

use lightr_core::ResourceLimits;
use lightr_engine::{engine_for, EngineKind, ExecSpec, ResolvedMount};
use lightr_run::{run_vz_memoized_with, VzMemoKey};
use lightr_store::Store;

use crate::exit::die_lightr;

use super::super::vz_guest::VzGuestRun;
use super::super::RunJson;

// ── vz-memo path (the product's core moat) ───────────────────────────────────
// A non-detached `vz` rootfs run is MEMOIZABLE like the native path (see the
// module doc): 1st run boots the VM + captures {exit,stdout,stderr}; an
// identical 2nd run is a HIT replayed from the AC with NO VM boot.
//
// ADR-0024 D4: `guest` carries the resolved argv/env/user/workdir (image config
// < CLI), `volumes` the `-v` host dirs, `shm_size` the `--shm-size`. All but
// the volumes enter the key; a run with volumes is never replayed nor stored
// (live host dirs are not content-addressed).
#[allow(clippy::too_many_arguments)]
pub(crate) fn run_vz_memo(
    engine_kind: EngineKind,
    ref_name: &str,
    guest: &VzGuestRun,
    volumes: &[ResolvedMount],
    shm_size: Option<u64>,
    store: &Store,
    cwd: &std::path::Path,
    limits: ResourceLimits,
    json: bool,
) -> i32 {
    // 1. Resolve the rootfs ref → its content digest (the image identity for
    //    the key), exactly like a mount's key contribution in assemble_key:
    //    the ref's CURRENT root digest. A missing ref fails closed.
    let rootfs_digest = match store.ref_get(ref_name) {
        Ok(Some(rec)) => rec.root,
        Ok(None) => {
            eprintln!("lightr: run: rootfs ref not found: {ref_name}");
            return 1;
        }
        Err(e) => return die_lightr(&e),
    };

    // 2. Key on what the guest applies: the effective argv, the env exactly as
    //    the engine builds it (GUEST_PATH < image ENV < -e; one function,
    //    `vzguest::guest_env`, so key and guest cannot drift), and the raw
    //    user/workdir/shm inputs. HOME derives from user + the image's passwd,
    //    both covered (rootfs_digest).
    let command = guest.argv.as_slice();
    let key = VzMemoKey {
        command: command.to_vec(),
        rootfs_digest,
        env: lightr_engine::engine::vzguest::guest_env(&guest.env),
        user: guest.user.clone(),
        workdir: guest.workdir.clone(),
        shm_size,
    };

    // 3. Memoize. On a HIT the closure is never invoked (no VM boot). On a
    //    MISS the closure hydrates the rootfs, boots the VM via the engine,
    //    and reads the guest's stdout/stderr capture files back off the
    //    rootfs share (with a brief retry for virtiofs flush lag — the same
    //    pattern the engine uses for EXIT_FILE).
    let cwd_buf = cwd.to_path_buf();
    let outcome = run_vz_memoized_with(&key, store, volumes.is_empty(), || {
        // Hydrate the rootfs ref CoW into a temp dir for this boot.
        let tmp = tempfile::TempDir::new().map_err(lightr_core::LightrError::Io)?;
        lightr_index::hydrate(tmp.path(), store, ref_name)?;
        let rootfs_path = tmp.path().to_path_buf();

        let engine = engine_for(engine_kind)?;
        let spec = ExecSpec {
            cwd: &cwd_buf,
            command,
            rootfs: Some(rootfs_path.as_path()),
            limits,
            net: false,         // vz-memo path is non-detached + non-networked
            net_isolate: false, // vz isolates via its VM; no netns flag needed
            net_fd: None,       // no mesh NIC on the memo path (ADR-0018)
            net_mac: None,
            mounts: volumes,
            env: &guest.env,
            workdir: guest.workdir.as_deref(),
            user: guest.user.as_deref(),
            hostname: None,
            add_host: &[],
            dns: &[],
            mesh_ip: None,
            // WP-#92: --read-only is not applied on vz (its own VM). ADR-0024 D4:
            // --shm-size sizes the guest /dev/shm tmpfs.
            read_only: false,
            shm_size,
            // WP-#94: capability enforcement is the ns engine's job; the vz-memo
            // path is its own VM. Defaults (no cap changes).
            cap_drop: &[],
            cap_add: &[],
            init: false,
            // WP-#99: CRI-only carry-slots; the vz-memo path never joins a netns
            // nor names a cgroup leaf (it is its own VM). Defaults.
            join_netns: None,
            cgroup_name: None,
            // WP-#102: vz-memo path is its own VM; no exec-readiness pipe. None.
            exec_ready_fd: None,
            // WP-#106: vz LSM lives inside the guest; no ns aa_change_onexec. None.
            apparmor: None,
            // WP-#108: vz seccomp lives inside the guest; no ns filter install. None.
            seccomp: None,
            // WP-#107: no CRI volume mounts / DNS / hostname here.
            bind_mounts: &[],
            resolv_conf: None,
            tmpfs: &[],
            // --ulimit: the vz-memo path is its own VM; no ns setrlimit here.
            ulimits: &[],
            // --oom-score-adj: the vz-memo path is its own VM; OOM tuning lives in
            // the guest. None.
            oom_score_adj: None,
        };
        // Suppress the guest CONSOLE (boot log + exit marker) from the host's
        // stdout on a memo MISS: real stdout/stderr come from the capture files
        // below, so the console is noise that would prepend the boot log (and
        // make a MISS look unlike a HIT). The shim still taps the pipe for the
        // exit marker (tap precedes forward), so force-stop is unaffected.
        // Respect an explicit LIGHTR_VZ_CONSOLE (user debugging).
        if std::env::var_os("LIGHTR_VZ_CONSOLE").is_none() {
            // Safety: single-threaded here, before the engine spawns the VM.
            unsafe { std::env::set_var("LIGHTR_VZ_CONSOLE", "/dev/null") };
        }
        let exit = engine.run(&spec)?;

        // Read the guest's stdout/stderr capture files off the rootfs share.
        // PID1 fsyncs them BEFORE the console marker the engine waits on; the
        // retry loop covers virtiofs flush lag (~30×100ms), mirroring the
        // engine's EXIT_FILE read. Constants pinned to lightr_init::{STDOUT_FILE,
        // STDERR_FILE}, kept inline to avoid a new crate dependency.
        const STDOUT_FILE: &str = "/.lightr-stdout";
        const STDERR_FILE: &str = "/.lightr-stderr";
        let stdout_path = rootfs_path.join(STDOUT_FILE.trim_start_matches('/'));
        let stderr_path = rootfs_path.join(STDERR_FILE.trim_start_matches('/'));

        let read_capture = |path: &std::path::Path| -> Vec<u8> {
            for _ in 0..30 {
                if let Ok(bytes) = std::fs::read(path) {
                    return bytes;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            // A missing capture file is an empty stream (never an error): the
            // exit code is authoritative, and a non-zero exit isn't cached
            // anyway. Empty + exit==0 is a legitimately empty-output run.
            Vec::new()
        };
        let stdout = read_capture(&stdout_path);
        let stderr = read_capture(&stderr_path);

        // Keep the temp dir alive until after the files are read.
        drop(tmp);

        Ok((exit, stdout, stderr))
    });

    let outcome = match outcome {
        Ok(o) => o,
        Err(e) => return die_lightr(&e),
    };

    // 4. Replay: write stdout then stderr raw (lossless), print the memo
    //    marker to stderr, exit = the (possibly replayed) exit code. Mirrors
    //    the native handler's streaming + marker.
    let hex = outcome.key.to_hex();
    let short = &hex[..16];
    let hit_str = if outcome.hit { "HIT" } else { "MISS" };
    eprintln!("lightr: memo {hit_str} key={short}");
    {
        let stdout = std::io::stdout();
        let mut out = stdout.lock();
        out.write_all(&outcome.stdout).ok();
    }
    {
        let stderr = std::io::stderr();
        let mut err = stderr.lock();
        err.write_all(&outcome.stderr).ok();
    }

    if json {
        let obj = RunJson {
            key: hex.clone(),
            hit: outcome.hit,
            exit_code: outcome.exit_code,
        };
        eprintln!(
            "lightr-json: {}",
            serde_json::to_string(&obj).expect("serialize run")
        );
    }

    outcome.exit_code
}

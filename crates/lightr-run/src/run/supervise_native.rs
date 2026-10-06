//! WP-RC-RESTART — the native detached supervisor + its `--restart` re-spawn
//! loop (the heart). Moved out of `supervise.rs` so each file stays under the
//! 400-line godfile cap. The vz container path stays in `svz.rs`; `supervise`
//! dispatches here for the native host-process case.
//!
//! Shape: one-time setup (mount hydration, log files, port forwarders, health
//! config, the ctl endpoint) → an OUTER restart loop that spawns the child,
//! monitors it (serving ctl + probing health), and on exit consults the
//! `RestartPolicy`. `no` (the default) runs the child exactly once and exits —
//! byte-identical to the pre-WP-RC-RESTART supervisor. `always`/`unless-stopped`
//! re-spawn until an explicit stop; `on-failure[:max]` re-spawns on a nonzero
//! exit up to `max`. A small crash-loop backoff bounds a tight failure loop, and
//! an explicit `lightr stop`/`rm` (a stop marker, or a signal relayed through
//! ctl.sock) disables every restart.

use lightr_core::{LightrError, Result};
use lightr_store::Store;
use std::path::PathBuf;

#[cfg(windows)]
use super::ctl::ctl_sock_path;
use super::memo::validate_mount_target;
use super::respawn;
use super::types::{MountOnDisk2, SpecOnDisk};
use crate::restart::RestartPolicy;

pub(super) fn supervise_native(
    dir: &std::path::Path,
    spec: &SpecOnDisk,
    store: &Store,
) -> Result<i32> {
    let cwd = PathBuf::from(&spec.cwd);
    if named_volumes(spec).len() > 1 || (!named_volumes(spec).is_empty() && spec.restart.is_some())
    {
        return Err(LightrError::InvalidRef(
            "named-volume runtime currently supports one non-restarting mount".to_string(),
        ));
    }
    #[cfg(not(target_os = "linux"))]
    if !named_volumes(spec).is_empty() {
        return Err(LightrError::InvalidRef(
            "named-volume runtime unsupported: atomic lock and stable process token required"
                .to_string(),
        ));
    }

    // Bind the control socket before any work starts (volume ownership, mount
    // hydration, forwarders, the child): a run that `stop`/`ps` cannot reach
    // must not start. The guard removes `ctl.sock` on every later error return.
    #[cfg(unix)]
    let ctl = super::ctl::bind_ctl_listener(dir)?;

    let volumes = named_volumes(spec);
    let mut pending = Vec::new();
    for (name, _) in &volumes {
        // Validate the pre-existing registry before begin_owner can create its
        // `.lightr/` lock directory. A missing/corrupt named mount leaves no
        // owner artifact behind.
        lightr_store::volume::inspect(store.root(), name)?;
        match lightr_store::volume::begin_owner(store.root(), name, dir) {
            Ok(owner) => pending.push((name.clone(), owner)),
            Err(error) => {
                return Err(cleanup_error(error, store.root(), &pending));
            }
        }
    }

    // Hydrate mounts (same law as run_memoized), once for the run's lifetime.
    for m in &spec.mounts {
        validate_mount_target(&m.target)?;
        let dest = cwd.join(&m.target);
        if let Err(error) = lightr_index::hydrate(&dest, store, &m.ref_name) {
            return Err(cleanup_error(error, store.root(), &pending));
        }
    }

    // WP-RUNFLAGS: materialize the persisted `-v/--volume` host binds + `--tmpfs`
    // scratch dirs (the tagged `mounts2` shape) once for the run's lifetime, the
    // same way the synchronous memo path does. Empty ⇒ no-op (behaviour-preserving).
    if let Err(error) = super::bindmat::materialize_mounts2(&cwd, store.root(), &spec.mounts2) {
        return Err(cleanup_error(error, store.root(), &pending));
    }

    // WP-RC-WORKDIR: honor `-w`/`--workdir` as the child's cwd (Docker WORKDIR),
    // creating it if absent. `None` ⇒ `cwd` unchanged + no mkdir.
    let run_cwd = match super::spawn::resolve_workdir(&cwd, spec.workdir.as_deref()) {
        Ok(path) => path,
        Err(error) => {
            return Err(cleanup_error(error, store.root(), &pending));
        }
    };

    // WP-RC-RESTART: resolve the persisted policy. `None`/unparseable ⇒ `No`
    // (run once + exit, byte-identical to before).
    let policy = respawn::policy_from_spec(spec.restart.as_deref());

    // F-309 / WP-RC-4: load an optional healthcheck (probed on the monitor loop).
    let health_cfg = match crate::healthcheck::load_for(dir) {
        Ok(config) => config,
        Err(error) => {
            return Err(cleanup_error(error, store.root(), &pending));
        }
    };

    #[cfg(unix)]
    return run_supervisor_loop(
        dir,
        ctl,
        spec,
        &run_cwd,
        policy,
        health_cfg,
        OwnerSetup {
            root: store.root(),
            volumes,
            pending,
        },
    );
    #[cfg(windows)]
    run_supervisor_loop(
        dir,
        spec,
        &cwd,
        &run_cwd,
        policy,
        health_cfg,
        OwnerSetup {
            root: store.root(),
            volumes,
            pending,
        },
    )
}

fn cleanup_error(
    error: LightrError,
    root: &std::path::Path,
    pending: &[(String, lightr_store::volume::VolumeOwner)],
) -> LightrError {
    for (name, owner) in pending {
        if let Err(cleanup) = lightr_store::volume::abandon_pending(root, name, owner.nonce()) {
            return LightrError::InvalidRef(format!(
                "{error}; named-volume pending cleanup failed: {cleanup}"
            ));
        }
    }
    error
}

// FIX-#76 (godfile split): the per-concern setup helpers (`spawn_child`,
// `maybe_auto_remove`, `start_forwarders`) live in `supervise_native_setup.rs`,
// pulled in via `#[path]`. Keeping them out of this file leaves the heart-loop
// under the 400-line cap after the teardown-order fix.
#[path = "supervise_native_setup.rs"]
mod setup;
#[cfg(unix)]
use setup::ExecBarrier;
use setup::{maybe_auto_remove, spawn_child, start_forwarders};

fn named_volumes(spec: &SpecOnDisk) -> Vec<(String, String)> {
    spec.mounts2
        .iter()
        .filter_map(|mount| match mount {
            MountOnDisk2::NamedVolume { source, target, .. } => {
                Some((source.clone(), target.clone()))
            }
            _ => None,
        })
        .collect()
}

struct OwnerSetup<'a> {
    root: &'a std::path::Path,
    volumes: Vec<(String, String)>,
    pending: Vec<(String, lightr_store::volume::VolumeOwner)>,
}

#[cfg(unix)]
fn run_supervisor_loop(
    dir: &std::path::Path,
    ctl: super::ctl::CtlListener,
    spec: &SpecOnDisk,
    run_cwd: &std::path::Path,
    policy: RestartPolicy,
    health_cfg: Option<crate::healthcheck::Healthcheck>,
    owners: OwnerSetup<'_>,
) -> Result<i32> {
    use std::io::{BufRead, BufReader, Write};
    use std::os::unix::process::ExitStatusExt;
    use std::time::{Duration, Instant};

    // Health probes run in the spec's cwd (not `-w`), as before.
    let cwd = PathBuf::from(&spec.cwd);
    // Forwarders + ctl endpoint (bound by the caller) live for the whole run
    // (across re-spawns).
    let _forwarders = start_forwarders(dir, spec);

    // Health state machine + monotonic launch instant (started once; `ps` shows
    // "starting" before the first probe round).
    let health_launched = Instant::now();
    let mut health_state = crate::healthcheck::HealthState::default();
    if health_cfg.is_some() {
        crate::healthcheck::write_state(dir, health_state.status);
    }
    let mut next_probe = Instant::now();

    // `stopped` latches an EXPLICIT stop (a `signal` op relayed through ctl.sock,
    // or the lifecycle/stop stop marker) so no policy re-spawns after it.
    let mut stopped = false;
    let mut restarts_done: u32 = 0;

    let final_exit = 'restart: loop {
        let barrier = (!owners.pending.is_empty())
            .then(ExecBarrier::new)
            .transpose()?;
        let (mut child, child_pid) = match spawn_child(dir, spec, run_cwd, barrier.as_ref()) {
            Ok(child) => child,
            Err(error) => {
                for (name, owner) in owners.pending {
                    let _ =
                        lightr_store::volume::abandon_pending(owners.root, &name, owner.nonce());
                }
                return Err(error);
            }
        };
        for ((name, target), (_, owner)) in owners.volumes.iter().zip(&owners.pending) {
            let mount_id = format!("{name}:{target}");
            if let Err(error) = lightr_store::volume::activate_owner(
                owners.root,
                name,
                dir,
                owner.nonce(),
                dir.file_name()
                    .and_then(|id| id.to_str())
                    .unwrap_or_default(),
                child_pid,
                &mount_id,
            ) {
                kill_and_reap(&mut child, child_pid);
                for (name, owner) in &owners.pending {
                    let _ = lightr_store::volume::abandon_pending(owners.root, name, owner.nonce());
                }
                return Err(error);
            }
        }
        if let Some(barrier) = &barrier {
            if let Err(error) = barrier.release() {
                kill_and_reap(&mut child, child_pid);
                return Err(error);
            }
        }

        // Per-child monitor: serve ctl.sock + poll child + probe health.
        let exit_code = loop {
            if let Some(ref hc) = health_cfg {
                if Instant::now() >= next_probe {
                    let passed = crate::healthcheck::probe_once(hc, &cwd);
                    let in_start = health_launched.elapsed().as_secs() < hc.start_period_s;
                    health_state.record(passed, in_start, hc.retries);
                    crate::healthcheck::write_state(dir, health_state.status);
                    next_probe = Instant::now() + Duration::from_secs(hc.interval_s.max(1));
                }
            }

            if let Some(status) = child.try_wait().map_err(LightrError::Io)? {
                break status
                    .code()
                    .unwrap_or_else(|| 128 + status.signal().unwrap_or(0));
            }

            match ctl.listener.accept() {
                Ok((stream, _)) => {
                    stream.set_read_timeout(Some(Duration::from_secs(1))).ok();
                    stream.set_write_timeout(Some(Duration::from_secs(1))).ok();
                    let mut reader = BufReader::new(&stream);
                    let mut line = String::new();
                    if reader.read_line(&mut line).is_ok() {
                        let line = line.trim();
                        if let Ok(req) = serde_json::from_str::<serde_json::Value>(line) {
                            let op = req.get("op").and_then(|v| v.as_str()).unwrap_or("");
                            let reply: serde_json::Value = match op {
                                "status" => serde_json::json!({"status": "running"}),
                                "signal" => {
                                    if let Some(sig) = req.get("sig").and_then(|v| v.as_i64()) {
                                        // WP-RC-RESTART: a signal relayed through
                                        // ctl.sock is the `stop`/`kill` path — an
                                        // EXPLICIT stop. Latch it (+ persist the
                                        // marker) so no policy re-spawns the child.
                                        stopped = true;
                                        respawn::write_stop_marker(dir);
                                        // WP-HYG (#71): signal the child's whole
                                        // PROCESS GROUP (negative pid) so the stop
                                        // reaches every descendant, not just `sh`.
                                        unsafe {
                                            libc::kill(-child_pid, sig as libc::c_int);
                                        }
                                        serde_json::json!({"ok": true})
                                    } else {
                                        serde_json::json!({"ok": false})
                                    }
                                }
                                _ => serde_json::json!({"error": "unknown op"}),
                            };
                            let mut reply_bytes = serde_json::to_vec(&reply).unwrap_or_default();
                            reply_bytes.push(b'\n');
                            let mut w = &stream;
                            let _ = w.write_all(&reply_bytes);
                        }
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => {}
            }

            std::thread::sleep(Duration::from_millis(100));
        };

        // Also honor a stop marker written by the lifecycle/stop DIRECT-kill path
        // (no ctl round-trip), so `rm -f` / a kill-without-ctl disables restart.
        if respawn::stop_requested(dir) {
            stopped = true;
        }

        if !respawn::should_restart(policy, exit_code, restarts_done, stopped) {
            break 'restart exit_code;
        }

        // Re-spawn: bump the count, back off (bounds a crash-loop), reflect the
        // restart in the status file so `ps`/watchers see movement.
        restarts_done = restarts_done.saturating_add(1);
        std::fs::write(dir.join("status"), format!("restarting {restarts_done}"))
            .map_err(LightrError::Io)?;
        std::thread::sleep(respawn::backoff_for(restarts_done));
    };

    // FIX-#76 (teardown TOCTOU): remove the ctl socket FIRST, THEN write the
    // terminal status. Readers (`is_running`/`run_status`/`ps`/`wait_run`) gate
    // liveness on socket-PRESENT; writing "exited" before removing the socket left
    // a window where a reader saw socket-present (→ "running") while the status
    // already said "exited" — the two disagreed. Removing the socket first means
    // once any reader observes the socket gone (→ not-running), the terminal status
    // is already (about to be) written, so the two are never contradictory.
    drop(ctl);
    write_terminal_status(dir, final_exit)?;
    for (name, _) in &owners.volumes {
        lightr_store::volume::terminal_run_owner(dir)?;
        lightr_store::volume::release_owner(owners.root, name, dir)?;
    }
    // WP-RUNFLAGS: `--rm` auto-clean on final exit (no-op unless `rm`).
    maybe_auto_remove(dir, spec);
    Ok(final_exit)
}

#[cfg(unix)]
fn kill_and_reap(child: &mut std::process::Child, pid: i32) {
    unsafe { libc::kill(-pid, libc::SIGKILL) };
    unsafe { libc::kill(pid, libc::SIGKILL) };
    let _ = child.wait();
}

#[cfg(unix)]
fn write_terminal_status(dir: &std::path::Path, code: i32) -> Result<()> {
    let status = dir.join("status");
    std::fs::write(&status, format!("exited {code}")).map_err(LightrError::Io)?;
    std::fs::File::open(&status)
        .map_err(LightrError::Io)?
        .sync_all()
        .map_err(LightrError::Io)
}

#[cfg(windows)] // WIN-PATH: named-pipe control server, identical JSON wire protocol.
fn run_supervisor_loop(
    dir: &std::path::Path,
    spec: &SpecOnDisk,
    cwd: &std::path::Path,
    run_cwd: &std::path::Path,
    policy: RestartPolicy,
    health_cfg: Option<crate::healthcheck::Healthcheck>,
    _owners: OwnerSetup<'_>,
) -> Result<i32> {
    let _ = (&_owners.root, &_owners.volumes, &_owners.pending);
    use super::ctl::ctl_pipe_name;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::time::{Duration, Instant};

    let _forwarders = start_forwarders(dir, spec);

    let sentinel = ctl_sock_path(dir);
    let pipe_name = ctl_pipe_name(dir);

    let health_launched = Instant::now();
    let mut health_state = crate::healthcheck::HealthState::default();
    if health_cfg.is_some() {
        crate::healthcheck::write_state(dir, health_state.status);
    }
    let mut next_probe = Instant::now();

    let mut restarts_done: u32 = 0;

    let final_exit = 'restart: loop {
        let (mut child, child_pid) = spawn_child(dir, spec, run_cwd)?;

        // Per-child named-pipe control server (one server per child, like the
        // unix ctl.sock is served per-iteration here). A `signal` op writes the
        // stop marker (win path), which the post-exit check reads.
        let done = Arc::new(AtomicBool::new(false));
        let done_srv = Arc::clone(&done);
        let server_exited = Arc::new(AtomicBool::new(false));
        let server_exited_srv = Arc::clone(&server_exited);
        let pipe_name_srv = pipe_name.clone();
        let dir_srv = dir.to_path_buf();
        let server = std::thread::spawn(move || {
            win::win_pipe_server_loop(&pipe_name_srv, child_pid, &dir_srv, &done_srv);
            server_exited_srv.store(true, Ordering::SeqCst);
        });
        std::fs::write(&sentinel, b"live").map_err(LightrError::Io)?;

        let exit_code = loop {
            if let Some(ref hc) = health_cfg {
                if Instant::now() >= next_probe {
                    let passed = crate::healthcheck::probe_once(hc, cwd);
                    let in_start = health_launched.elapsed().as_secs() < hc.start_period_s;
                    health_state.record(passed, in_start, hc.retries);
                    crate::healthcheck::write_state(dir, health_state.status);
                    next_probe = Instant::now() + Duration::from_secs(hc.interval_s.max(1));
                }
            }
            if let Some(status) = child.try_wait().map_err(LightrError::Io)? {
                break status.code().unwrap_or(1);
            }
            std::thread::sleep(Duration::from_millis(100));
        };

        // Tear down this child's pipe server before deciding on a re-spawn.
        done.store(true, Ordering::SeqCst);
        while !server_exited.load(Ordering::SeqCst) {
            win::win_pipe_nudge(&pipe_name);
            std::thread::sleep(Duration::from_millis(20));
        }
        let _ = server.join();

        let stopped = respawn::stop_requested(dir);
        if !respawn::should_restart(policy, exit_code, restarts_done, stopped) {
            break 'restart exit_code;
        }

        restarts_done = restarts_done.saturating_add(1);
        std::fs::write(dir.join("status"), format!("restarting {restarts_done}"))
            .map_err(LightrError::Io)?;
        std::thread::sleep(respawn::backoff_for(restarts_done));
    };

    // FIX-#76 (teardown TOCTOU): remove the ctl sentinel FIRST, THEN write the
    // terminal status — same ordering rationale as the unix path above (readers
    // gate liveness on the sentinel/socket being PRESENT).
    let _ = std::fs::remove_file(&sentinel);
    std::fs::write(dir.join("status"), format!("exited {final_exit}")).map_err(LightrError::Io)?;
    // WP-RUNFLAGS: `--rm` auto-clean on final exit (no-op unless `rm`).
    maybe_auto_remove(dir, spec);
    Ok(final_exit)
}

// WIN-PATH: the Windows named-pipe control-server helpers live in
// `supervise_win.rs`, pulled in via `#[path]`. `#[cfg(windows)]`, so the unix CI
// gate never compiles it.
#[cfg(windows)]
#[path = "supervise_win.rs"]
mod win;

#[cfg(test)]
#[path = "supervise_native_tests.rs"]
mod tests;

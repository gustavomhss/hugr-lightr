# ADR-0024 — `vz` guest exec over virtio-vsock and a container-like guest init

- **Status:** Proposed (2026-10-05). Not accepted; write no code against it until the
  owner accepts it.
- **Date:** 2026-10-05
- **Scope:** macOS `vz` engine only: Swift shim, `lightr-init` (guest PID 1), detached
  `vz` supervisor, `lightr exec`, `vz` flag policy. `ns`/`native`/`wsl` and ADR-0018
  networking are unchanged.
- **Evidence:** `file:line` references below at `1cde971`; a 2026-10-05 Orchestra spike
  (Ubuntu + Xvfb/xpra + VS Code + AT-SPI as a `vz` workload, owner's Intel Mac). Spike
  artifacts are local and outside the repo. Its footprint observations are not ledger
  measurements and are not claimed here.

## Context

Orchestra wants `lightr run --engine vz` to replace Docker for its Linux workspace.
Two gaps block it.

**1. No exec into a running `vz` guest.** `lightr exec` refuses `vz` runs before any
attempt (`crates/lightr-cli/src/handlers/exec.rs:35-43`). `docs/ARCHITECTURE.md:304`
lists `vz` exec as "planned". Orchestra runs a long-lived stdio line-protocol helper
plus short commands, so it needs stdin/stdout/stderr streams and real exit codes.
The spike's workaround was a file-drop loop: the workload polls a rootfs-share
directory every 200 ms, runs each dropped script and writes `.out`/`.rc` for the
host to poll (spike `guest/boot.sh:12`, `gexec`). That loop has no stdin, no
streaming and no signals. Its polling latency stacks on virtiofs visibility lag (the
shim documents ~1.3 s for `EXIT_FILE`, `crates/lightr-engine/shim/vz.swift:241-245`).

**2. The guest init only runs the workload.** After the rootfs mount and `chroot`
(`crates/lightr-init/src/lib.rs:186-224`), PID 1 spawns the command with a cleared
env and waits for that one child (`crates/lightr-init/src/bin/init.rs:98-157`). It
does not mount `/proc`, `/sys`, `/dev`, `/dev/pts`, `/dev/shm` or `/tmp`, does not
bring up `lo`, and does not reap orphans. The spike did all of that in a shell
workload (`guest/boot.sh:1-9`) and switched users with `setpriv` (`:11`).

Several flags are dropped without error on `vz`, which violates principle 7 and
`CONTRIBUTING.md` "Fail-closed":

| Flag | Where it is lost |
|---|---|
| `-e` | engine overwrites guest env with `PATH` only (`engine/vz.rs:174`, `:325`); callers pass `env: &[]` (`lightr-run/src/run/svz.rs:170`, `lightr-cli/src/handlers/run/paths_vz.rs:79`) |
| `-u` | `user: None` (`svz.rs:172`, `paths_vz.rs:81`); inventory says `vz: "unsupported"` but nothing refuses it (`handlers/run/policy_security_inventory.json:4`) |
| `-v` | `mounts: &[]` (`svz.rs:169`, `paths_vz.rs:78`); shim shares only `rootfs`/`store` (`shim/vz.swift:209-226`) |
| `-w` | `workdir: None` (`svz.rs:171`); guest cwd is always `/` (`vz.rs:173`) |
| `--hostname`/`--dns`/`--add-host` | passed by the supervisor (`svz.rs:173-175`); `InitSpec` has no such fields (`lightr-init/src/lib.rs:90-104`) |

The policy layer already refuses `--tmpfs`, `--ulimit` and `--pids-limit` on `vz`
(`handlers/run/policy.rs:124-141`, `:161-170`). The rule exists; these rows were never
added.

**The vsock claim.** Code and docs say "macOS has NO host AF_VSOCK" (`vz.rs:140`,
`lightr-init/src/lib.rs:11`, `docs/ARCHITECTURE.md:157`). The statement is correct
as written: `socket(AF_VSOCK)` returns ENODEV on macOS (`docs/decisions-log.md:212-216`).
It does not follow that there is no host-to-guest vsock.
Virtualization.framework provides `VZVirtioSocketDeviceConfiguration` /
`VZVirtioSocketDevice` (macOS 11+, not architecture-gated). The VM-owning process can
`connect(toPort:)` / `setSocketListener(_:forPort:)` and receive a
`VZVirtioSocketConnection` carrying an ordinary fd. The decisions log recorded this
as option (b) and deferred it because exit-code delivery alone did not justify it
(`decisions-log.md:221-225`); exec does. The shim configures no socket device today
(`shim/vz.swift:312-316`, `:522-527`).

## Decision

### D1. Transport: `VZVirtioSocketDevice`, bridged by the run's supervisor

`lightr exec` → `<run_dir>/exec.sock` (AF_UNIX) → supervisor →
`VZVirtioSocketDevice.connect(toPort: AGENT_PORT)` → guest agent (AF_VSOCK listener).

- **No daemon.** Only the VM-owning process can open vsock. For a detached `vz` run
  that is the supervisor, which already boots the VM in-process and serves `ctl.sock`
  (`svz.rs:11-29`, `:296-330`). The supervisor lives only as long as the run, and the
  agent runs inside the VM, so principle 1 holds.
- **Byte splice.** For each `exec.sock` connection the supervisor opens one vsock
  connection and copies bytes in both directions. It never parses frames, so the
  guest agent is the single framing owner.
- **Shim ABI.** Add `config.socketDevices = [VZVirtioSocketDeviceConfiguration()]` and
  `lightr_vz_session_vsock_connect(handle, port, *out_fd)`, which runs on the session
  queue, `dup`s the fd and retains the connection until close. This needs a VM
  handle, and the legacy `lightr_vz_run` is one blocking call with none
  (`shim/vz.swift:113`). So the detached path moves to the retained-session ABI
  (create/start/stop/destroy), and that ABI's `#if !arch(arm64)` gate
  (`shim/vz.swift:463-466`, `:544-547`) narrows to save/restore, the only calls Apple
  restricts. This is the same narrowing D6 applies to the probe.
- **Rejected: a published TCP port in the guest** (spike `guest/boot2.sh:13-16`). It
  needs the NAT NIC plus DHCP on every exec-capable run. It listens on the vmnet
  subnet, where local processes and other guests can reach it, so it needs an in-band
  credential. It also adds port-clash and forwarder failure modes.
- **Rejected: virtiofs file drop** (spike `gexec`). It polls, has no stdin and no
  signals, and its exit semantics ride on share flush ordering the code already works
  around (`vz.rs:273-286`). It stays correct for its existing one-shot use
  (`CMD_FILE`/`EXIT_FILE`), which this ADR does not change.

### D2. Guest agent and PID 1

- **PID 1 (`lightr-init`)** keeps the lifecycle. It mounts, reads `InitSpec`,
  `chroot`s and applies D4. Then it forks the agent, spawns the workload and loops on
  `waitpid(-1)` to reap every orphan (today it waits only its own child, `init.rs:145`).
  When the workload exits, PID 1 sends SIGKILL to all exec process groups, reports
  through the existing console-marker + `EXIT_FILE` channel, and powers off. Run
  lifetime equals workload lifetime, as in Docker.
- **The agent** is a child that PID 1 forks after `chroot`. It is the same in-memory
  image, so it needs no binary in the user rootfs. It listens on `AF_VSOCK`
  `AGENT_PORT`, one constant in `lightr-init` shared with the host. PID 1 does not
  restart a dead agent: later execs fail with "guest agent unavailable" and the
  workload is unaffected.
- **Authentication is by transport, with no secrets.**
  1. `exec.sock` is mode `0600` in a `0700` run dir, and the supervisor rejects any
     peer whose `getpeereid` uid differs from its euid. Today's `ctl.sock` has no such
     check (`lightr-run/src/run/ctl.rs:39-60`), so it is not reused.
  2. macOS has no host-global AF_VSOCK, so only the VM-owning process can reach guest
     vsock ports.
  3. The agent accepts only peers with source CID `VMADDR_CID_HOST` (2). This rejects
     guest-local callers, so a guest workload cannot use the agent to escalate to root.
- **Framing.** One vsock connection carries one exec, with no multiplexing, so the
  long-lived helper and short commands stay independent. A frame is
  `type:u8 | len:u32be | payload` with `len <= 64 KiB`. Types: `OPEN` (JSON with `v`,
  argv, env, cwd, user, `tty`, `stdin`, rows/cols), `STDIN`, `STDIN_EOF`, `SIGNAL`
  (u8), `RESIZE`, `STDOUT`, `STDERR`, `EXIT` (code or signal), `ERROR` (reason). An
  unknown `v` or frame type gets `ERROR`, then close.
- **Exit and signals.** `EXIT` maps to the code or to `128+sig` (as in `init.rs:259`).
  A spawn failure maps to 126/127 (as with `SPAWN_FAILED_CODE`). A connection that
  closes without `EXIT` maps to 255, never 0 (as with `GUEST_NO_REPORT_CODE`,
  `vz.rs:23`). The CLI forwards SIGINT/SIGTERM/SIGHUP as `SIGNAL` frames. Each exec
  runs under `setsid`, and signals go to its process group.
- **TTY is optional.** With `-t`, the agent allocates a pty from `/dev/ptmx` (needs
  D4's devpts), merges stderr into stdout as Docker does, and handles `RESIZE`.
  Without `-t`, stdio uses pipes. Without `-i`, stdin is `/dev/null`.
- **Exec lifetime follows the connection.** If the host side disconnects, the agent
  sends SIGKILL to that exec's process group, so no orphan helper outlives its
  caller. `exec -d` is refused in v1.
- **Defaults.** An exec inherits the run's applied env, user and workdir. `exec -e`,
  `-u` and `-w` override them using D4's resolution rules.

### D3. `ps`, `stop` and the run boundary

- `ps` is unchanged (exec sessions are not runs). `stop` gains a graceful phase. The supervisor asks the agent, over a control
  connection on the same port, to deliver the run's stop signal (`stop.rs:38-46`) to
  the workload. After the stop timeout it falls back to today's force-stop (an
  `EXIT_FILE` write, `svz.rs:319-327`). Today a `vz` stop never delivers SIGTERM into
  the guest. After `stop` or workload exit, no `lightr` process remains and both
  sockets are removed.
- Exec targets detached `vz` runs (`-d --rootfs`) only. A foreground run, a run that
  is not running, and a retained or suspended snapshot session each get an explicit
  error naming the requirement. vsock connections are not part of saved machine
  state, so exec across suspend/resume (ADR-0014/0020) is deferred.

### D4. Container-like guest init: apply or refuse, never drop

After `chroot` and before the agent and workload start, PID 1 performs these steps.
Any failure fails the boot closed: a console diagnostic and no `EXIT_FILE`, so the
host sees 255 (`vz.rs:20-23`).

| Step | Detail |
|---|---|
| `/proc` | `proc`, `nosuid,nodev,noexec` |
| `/sys` | `sysfs`, read-only, `nosuid,nodev,noexec` |
| `/dev` | `devtmpfs`. `DEVTMPFS_MOUNT` (`scripts/build-kernel-x86.sh:106`) covers only the initramfs root, not the chroot. |
| `/dev/pts` | `devpts` `newinstance,ptmxmode=0666,mode=0620,gid=5`; `/dev/ptmx` → `pts/ptmx` |
| `/dev/shm` | `tmpfs` `1777`, size from `--shm-size`, else 64 MiB |
| `/tmp` | `tmpfs` `1777`. Deliberately unlike Docker: keeps scratch and AF_UNIX sockets (X11, D-Bus) off the host-shared virtiofs rootfs, where socket behaviour is unverified. |
| `lo` | `SIOCSIFFLAGS IFF_UP\|IFF_RUNNING` (spike `guest/boot.sh:9`) |

- **`-e`** fills `InitSpec.env` in order `GUEST_PATH`, then image `ENV`, then `-e`;
  later values win. The `vz` memo key must hash the applied env. Today it hashes a
  fixed `PATH` (`paths_vz.rs:45-53`), and ADR-0023 shows that a key ignoring applied
  env replays wrong results.
- **`-u`** adds `InitSpec.user {uid,gid,groups}`. The host resolves `name[:group]`
  against the hydrated rootfs `/etc/passwd` and `/etc/group` before boot. The rootfs is
  a host dir (`svz.rs:62-64`), so a bad user fails before any VM starts. In the guest,
  the child calls `setgroups` → `setgid` → `setuid` before `exec`. On failure the
  child exits non-zero and is never run as root (ns parity #113/#114,
  `docs/spec/parity-audit.md:87`).
- **`-v`** adds one `VZVirtioFileSystemDeviceConfiguration` per volume (tags
  `vol0..N`, `readOnly` from `:ro`) and `InitSpec.volumes {tag,target,ro}`. PID 1
  mounts each volume inside the chroot. A non-directory source (VZ shares directories
  only), a missing source, or a shim validation failure is an explicit error before
  boot.
- **`-w`** sets `InitSpec.cwd`; a missing directory fails the spawn with 126.
- **`--hostname`/`--dns`/`--add-host`**, and any other flag that reaches the `vz` path
  without being applied, are refused by `policy.rs` (exit 2) until implemented. The
  inventory drops `"unsupported"` for `vz`: every `vz` row becomes `enforced` or
  `refused`, and `-e` and `-v` gain rows.
- **Version skew fails closed.** `InitSpec` lacks `deny_unknown_fields`, so an old
  initrd would ignore `user`/`volumes` and drop them without error. `pack.json` gains
  an integer `init_abi`. The host refuses `-e`/`-u`/`-v`/`-w`/`exec` with "linux pack
  too old, reinstall" when `init_abi` is below the required version.

### D5. Kernel and pack

Both kernel recipes enable `VSOCKETS` and `VIRTIO_VSOCKETS` and assert them with
fail-closed greps, like `VIRTIO_NET` (`scripts/build-kernel-x86.sh:111-121`;
`build-kernel-arm64.sh:84-91`). `UNIX98_PTYS`, `DEVPTS_FS` and `TMPFS` are asserted
too. Nothing relies on defconfig defaults.

### D6. Related regressions (note only; fix separately)

**Intel `vz` is disabled.** `37b14e5` (#143) gated `probe_vz` on
`target_arch = "aarch64"` (`crates/lightr-engine/src/engine/probe.rs:85`, `:112-119`).
`engine_for` refuses unavailable engines (`engine/mod.rs:108-115`), so
`run --engine vz` fails on Intel. Intel is the only platform the parity audit marks
runtime-validated for `vz` (`docs/spec/parity-audit.md:156`). The spike ran only after
locally removing this gate.

Recommended fix: restore `all(target_os = "macos", feature = "vz")`; keep the
arm64/macOS 14 gate on snapshot operations only, which already fail honestly
(`SuspendResume::Unsupported`, `vz.rs:368-373`, plus the shim's save/restore gate);
report snapshot capability as a separate probe detail; add an Intel CI assertion that
`engine ls` shows `vz` available when a pack is installed.

**Suspected, unverified at runtime.** `spawn_wait` reads `SUSPEND_GATE_FILE`
unconditionally after spawning the child (`init.rs:131-141`). `VzEngine::run` writes
that file only for suspend (`vz.rs:332-336`). An initrd built from current source
would therefore report 127 and power off on every ordinary run while the child is
still running. The spike's initrd (2026-06-18) predates #143, so the spike could not
have hit this. Fix: gate the PID proof on `spec.suspend_gate`.

## Acceptance criteria (Intel runbook; CI where a macOS `vz` runner exists)

1. `lightr exec <run> sh -c 'exit 7'` returns 7, `kill -TERM $$` returns 143, and
   `/nonexistent` returns 127. A run with no supervisor fails with an explicit error,
   not 0.
2. `printf 'a\nb\n' | lightr exec -i <run> cat` is byte-exact, with stdout and stderr
   kept separate. A line-protocol helper answers 1000 sequential request/response
   lines on one exec without reconnecting.
3. `lightr exec -t <run> tty` prints `/dev/pts/N`, and SIGINT to the CLI ends the guest
   process group.
4. Auth has teeth: a different uid connecting to `exec.sock` is rejected, and so is a
   guest-local connection to `AGENT_PORT`. Removing either check fails a named test.
5. Killing the exec CLI with SIGKILL leaves no guest process from that exec within
   2 s. After `lightr stop`, `pgrep -f lightr` is empty, both sockets are gone, and the
   workload received the stop signal before force-stop.
6. The guest can read `/proc/1/comm`. `mount` lists proc, sysfs, devtmpfs, devpts,
   shm and tmp. `ping -c1 127.0.0.1` succeeds. A double-fork orphan leaves 0 zombies
   (as `NS_INIT_REAP` does for ns).
7. `-e K=V` is visible, and changing it misses the memo. `-u 1000:1000` gives
   uid/gid 1000. An unresolvable `-u` fails before boot. A `-v dir:/m:ro` write fails
   with EROFS while the control write succeeds. Every `vz` inventory row is `enforced`
   or `refused`, and `--hostname` on `vz` exits 2.
8. When `init_abi` is below the required version, `-e`/`-u`/`-v`/`-w`/`exec` fail
   with the reinstall error.
9. On Intel with a pack installed, `engine ls` shows `vz` available, and `suspend`
   still returns `Unsupported`.

## Staging

1. D6 fixes (probe, gate read), with tests. These do not depend on this ADR.
2. Fail-closed policy: refuse every dropped `vz` flag and correct the inventory. This
   lands even if the rest of the ADR is rejected.
3. Guest init (D4 mounts, `lo`, reaper), `init_abi`, and the kernel asserts (D5).
4. `-e`, `-w`, `-u`, `-v` applied, with the memo-key change. Each flag moves from
   `refused` to `enforced` in the same PR as its test.
5. Exec: shim socket device and ABI narrowing, agent, `exec.sock` bridge, CLI. Replace
   `exec_vz_run_exits_1` with AC 1-5.
6. Graceful `stop` through the agent.

## Consequences

- Orchestra can drop the spike's file-drop channel and shell init, and use
  `lightr exec` the way it uses `docker exec`.
- The shim gains one device and one ABI call, and the detached path moves to the
  session ABI. The `swift_shim_*` source tests (`vz.rs:697-777`) must pin the new
  invariants.
- "macOS has no host AF_VSOCK" stays true. Every comment or doc that reads it as "no
  vsock channel" must be corrected.
- Open before acceptance: how virtiofs presents ownership and permissions to a
  non-root guest uid; how `VZVirtioSocketConnection` fds behave under the shim's
  serial-queue model on Intel (first spike task of stage 5).

# S5-NET — vz container networking: expected assertions + parity mapping

**Status (2026-06-18, Intel x86_64, macOS):** `run.sh` ran **GREEN** end-to-end
on this box — all 9 assertions PASS. This closes the `vz` half of **F-304**
(`-p` for a Linux image). Re-run `bash spikes/s5-vz-net/run.sh` to reproduce; it
exits 0 only when every assertion below passes.

**Re-run (2026-10-06):** GREEN twice on a `--features vz` release build of
`7682bf7` (host NAT cold, then warm). See "Host NAT readiness" below.

This is the networking sibling of `spikes/s5-vz-boot` (F-205/F-206, vz boot). It
proves the flagship Docker-parity case: **run a real Linux container with a
published port on a Mac, reach its server from the host, and tear it down
cleanly** — the case the Phase-1 guard used to reject as "Phase 2".

---

## What the harness proves

| Step | Assertion | Mechanism exercised |
|------|-----------|---------------------|
| 1–3 | toolchain present; `--features vz` builds; binary codesigned with `com.apple.security.virtualization` | the vz CLI is buildable + entitled (VZ refuses to start a VM without the entitlement) |
| 4 | a linux pack is installed whose `initrd` is the **current** `lightr-init` | the guest PID1 is this source tree's build — i.e. it contains `publish_ip` (writes the guest IP to `IP_FILE`); a stale initrd would never publish an IP |
| 5 | an `alpine` rootfs ref exists in the store | a real Linux image to boot as the container rootfs |
| 6 | `lightr run -d -p 18080:80 --engine vz --rootfs alpine -- <nc server>` prints the run id and returns immediately | the **detached vz path** routes through `spawn_detached_engine` → the supervisor boots the VM in-process (it does NOT block the CLI, unlike the old synchronous engine path that ignored `-d`) |
| 7 | `curl 127.0.0.1:18080` returns `lightr-vz-net` (the in-guest server's fixed 200 response) | END-TO-END: kernel `ip=dhcp` leased a NAT IP → guest PID1 published it to `IP_FILE` → the supervisor read it (`192.168.64.x`) and started a userspace forwarder `127.0.0.1:18080 → guest:80` → the host TCP round-trips through the forwarder into the busybox `nc` server inside the microVM |
| 8 | `lightr stop <id>` ⇒ status `exited`, and `curl` afterwards gets nothing | the supervisor's ctl handler writes the guest `EXIT_FILE`; the shim polls it and force-stops the VM (no new shim code); the forwarder is dropped (listener closed) ⇒ the published port is closed |
| 9 | no `lightr __supervise` process remains | the in-process VM dies with the supervisor; nothing is leaked (daemonless invariant holds for the container modality too) |

## Parity-audit row

**F-304** — networking (`-p`). The native detached path shipped in Phase 1
(`acceptance_net.rs`). This spike closes the **vz** path: `-p` for a Linux image
on macOS via the microVM, with a host→guest userspace forward and clean
teardown. Remaining Phase-2 items (container↔container networks, DNS/service
discovery, `-P`, udp, Linux `ns` veth/bridge) are tracked in `parity-audit.md`.

## Honesty notes

- vz virtualizes the **native** arch (Intel → x86_64 guest; this run was
  x86_64). The arm64 guest path shares the code but is validated separately
  (hardware-gated, `spikes/s5-vz-boot-arm64`).
- `lightr stop` exits with the stopped run's code (`143` = 128+SIGTERM), exactly
  like the native detached path — the harness asserts the closed port + `exited`
  status, not stop's own exit code.
- The in-guest server here is a fixed-response busybox `nc` loop (deterministic
  body for the assertion). A real image (nginx, etc.) publishes the same way —
  the forward is content-agnostic TCP.

## Host NAT readiness (2026-10-06, Intel i7-9750H, macOS 15.3.2)

A detached `vz` run always attaches the NAT NIC and boots with `ip=dhcp`
(`svz.rs` passes `net: true` with or without `-p`). A foreground run attaches
no NIC (`LIGHTR_VZ_NET` unset), so it never exercises DHCP. A green foreground
run therefore says nothing about detached networking.

`VZNATNetworkDeviceAttachment` is served by macOS InternetSharing (vmnet,
`bridge100` at `192.168.64.1`, `bootpd`). launchd starts InternetSharing on
demand when the VM process connects to `com.apple.NetworkSharing`. The guest
can lease only after `vmenet0` attaches. In the runs below, the guest console
shows `NETDEV WATCHDOG ... TX timeout` while kernel `ip=dhcp` retries, and only
while the NAT is not up yet. Those lines are a symptom of the host NAT. They do
not point at the kernel, initrd, MAC or cmdline.

Measured on 20 detached runs (the 2026-10-05 `--features vz` release build of
`e37a2e3`, code-identical to `7682bf7`; Alpine,
`--memory 1g`, default and `--cpus 2`/`3`, pack kernel `bcd58d2f…` = the F-304
and spike kernel). "NAT ready" is VM process spawn to `192.168.64.1` on
`bridge100` in the unified log. "Lease" is the guest's `IP-Config: Got DHCP
answer` timestamp:

| Runs | Host 1-min load | NAT ready | Guest lease | TX timeouts |
|---|---|---|---|---|
| 18 | 3.7–188 | 0.8–9.8 s | 0.36–4.1 s | 0 |
| `b1-default` (InternetSharing cold) | 22.7 | 24.0 s (InternetSharing spawn to `vmenet0`: 12.5 s) | 20.5 s | 2 |
| `b1-cpus2` (InternetSharing warm) | 103 | 18.5 s | 18.2 s | 1 |
| 2026-10-05 failing run | not recorded | never: the VM requested NetworkSharing 46 s after spawn; the supervisor's 60 s IP deadline tore it down 20 s later | none | ≥2 |

TX timeouts appeared only in the two runs where the NAT took 18 s or more, and
each guest leased right after the NAT came up. vCPU count does not separate
them (`b1-cpus2` stalled with 2 vCPUs). Neither does CPU load alone: 9 runs
with 12 or 48 busy-loop processes leased in ≤1.8 s. Both stalls coincided with
a load burst from other sessions (1-min load 23 to 103 within a minute) and
rising swap (2.1 to 3.9 GB used).

**Check before calling a detached `vz` failure a regression:** on a Step 7
failure `run.sh` prints the NAT timeline for the run window. If
`added addr=192.168.64.1` is missing, or comes after the supervisor's 60 s
deadline, the host NAT was not ready. Re-run on a quieter host before you
bisect lightr. The same check by hand:

```sh
/usr/bin/log show --start "<run start, local time>" --style compact \
  | grep -E "Successfully spawned (VirtualMachine|InternetSharing)|name=com.apple.NetworkSharing$|interface attach: vmenet|added addr=192.168.64.1"
```

Runbook preconditions added after the 2026-10-06 investigation:

- **The pack kernel must be a bzImage on x86_64.** Step 4 checks the `HdrS`
  setup-header magic. `~/.lightr/packs/linux/kernel` on this box is a vmlinux
  ELF (52 MB, 2026-06-12), which VZ rejects.
- **`LIGHTR_HOME` must be short.** The supervisor's `<run>/ctl.sock` must fit
  macOS's 103-byte AF_UNIX path. With a longer path, `stop` cannot reach the
  supervisor and falls back to SIGKILL (exit 137, status left `running`).
- **The run id is printed bare** since `1a41299` (2026-06-22). Step 6 accepts
  both formats.
- `LIGHTR_S5NET_BIN=<binary>` reuses an existing `--features vz` build instead
  of the Step 2 debug build.

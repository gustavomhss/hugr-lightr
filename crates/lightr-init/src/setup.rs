//! ADR-0024 D4: the container-like guest setup PID 1 performs after `chroot`
//! and before the workload starts, as DATA.
//!
//! [`guest_setup_plan`] is pure and host-tested; `bin/init.rs` executes the
//! steps in order with real `mount(2)`/`symlink(2)`/`ioctl(2)` calls and stops
//! at the first failure (fail closed: no `EXIT_FILE`, the host sees 255).

use serde::{Deserialize, Serialize};

/// `/dev/shm` size when the run sets no `--shm-size` (Docker's default).
pub const DEFAULT_SHM_BYTES: u64 = 64 * 1024 * 1024;

/// Mount flags the plan uses. Booleans rather than `MS_*` integers so the
/// library needs no libc; `bin/init.rs` maps them to `libc::MS_*`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MountFlags {
    pub rdonly: bool,
    pub nosuid: bool,
    pub nodev: bool,
    pub noexec: bool,
}

/// One `mount(source, target, fstype, flags, data)` call. `target` is an
/// absolute path inside the chrooted rootfs; PID 1 creates it if missing.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GuestMount {
    pub source: String,
    pub target: String,
    pub fstype: String,
    pub flags: MountFlags,
    pub data: String,
}

/// A step of the guest setup, executed in plan order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SetupStep {
    Mount(GuestMount),
    /// Replace `link` with a symlink to `target` (an existing node is removed).
    Symlink {
        target: String,
        link: String,
    },
    /// `SIOCSIFFLAGS IFF_UP|IFF_RUNNING` on `lo`.
    LoopbackUp,
}

/// A host directory shared into the guest (`-v host:target[:ro]`): the shim
/// adds one virtiofs device with `tag`, PID 1 mounts it at `target`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct GuestVolume {
    pub tag: String,
    pub target: String,
    pub readonly: bool,
}

/// Numeric identity the workload runs as. The host resolves names against the
/// image's `/etc/passwd` and `/etc/group` before boot; the guest only applies
/// `setgroups(groups)`, `setgid(gid)`, `setuid(uid)` in that order.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct GuestUser {
    pub uid: u32,
    pub gid: u32,
    pub groups: Vec<u32>,
}

/// The ordered setup for one boot: the D4 table, the `/dev` links, `lo`, then
/// the run's volumes (last, so a volume may cover `/tmp`).
pub fn guest_setup_plan(shm_size: Option<u64>, volumes: &[GuestVolume]) -> Vec<SetupStep> {
    let hardened = MountFlags {
        nosuid: true,
        nodev: true,
        noexec: true,
        ..MountFlags::default()
    };
    let mount = |source: &str, target: &str, fstype: &str, flags: MountFlags, data: String| {
        SetupStep::Mount(GuestMount {
            source: source.to_string(),
            target: target.to_string(),
            fstype: fstype.to_string(),
            flags,
            data,
        })
    };
    let link = |target: &str, link: &str| SetupStep::Symlink {
        target: target.to_string(),
        link: link.to_string(),
    };
    let mut plan = vec![
        mount("proc", "/proc", "proc", hardened, String::new()),
        mount(
            "sysfs",
            "/sys",
            "sysfs",
            MountFlags {
                rdonly: true,
                ..hardened
            },
            String::new(),
        ),
        // DEVTMPFS_MOUNT covers only the initramfs root, not the chroot.
        mount(
            "devtmpfs",
            "/dev",
            "devtmpfs",
            MountFlags {
                nosuid: true,
                ..MountFlags::default()
            },
            "mode=0755".to_string(),
        ),
        mount(
            "devpts",
            "/dev/pts",
            "devpts",
            MountFlags {
                nosuid: true,
                noexec: true,
                ..MountFlags::default()
            },
            "newinstance,ptmxmode=0666,mode=0620,gid=5".to_string(),
        ),
        mount(
            "shm",
            "/dev/shm",
            "tmpfs",
            hardened,
            format!("mode=1777,size={}", shm_size.unwrap_or(DEFAULT_SHM_BYTES)),
        ),
        // Unlike Docker: keeps scratch and AF_UNIX sockets (X11, D-Bus) off
        // the host-shared virtiofs rootfs.
        mount(
            "tmp",
            "/tmp",
            "tmpfs",
            MountFlags {
                nosuid: true,
                nodev: true,
                ..MountFlags::default()
            },
            "mode=1777".to_string(),
        ),
        link("pts/ptmx", "/dev/ptmx"),
        link("/proc/self/fd", "/dev/fd"),
        link("/proc/self/fd/0", "/dev/stdin"),
        link("/proc/self/fd/1", "/dev/stdout"),
        link("/proc/self/fd/2", "/dev/stderr"),
        SetupStep::LoopbackUp,
    ];
    plan.extend(volumes.iter().map(|v| {
        mount(
            &v.tag,
            &v.target,
            "virtiofs",
            MountFlags {
                rdonly: v.readonly,
                ..MountFlags::default()
            },
            String::new(),
        )
    }));
    plan
}

/// Human name of a step for the fail-closed diagnostic.
pub fn describe_step(step: &SetupStep) -> String {
    match step {
        SetupStep::Mount(m) => format!("mount {} ({}) at {}", m.source, m.fstype, m.target),
        SetupStep::Symlink { target, link } => format!("symlink {link} -> {target}"),
        SetupStep::LoopbackUp => "bring up lo".to_string(),
    }
}

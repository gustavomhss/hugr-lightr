//! Linux syscalls behind the ADR-0024 D4 guest setup and the PID 1 reaper,
//! split from `bin/init.rs` (house 400-line cap). Included only on Linux.

use lightr_init::GuestMount;
use std::ffi::CString;
use std::io;

/// PID 1 reaps EVERY child (ADR-0024 D2): wait on any pid until the
/// workload itself exits, discarding orphans re-parented to init. Returns
/// the workload's code (128+signal when killed).
pub(crate) fn reap_until(workload: libc::pid_t) -> io::Result<i32> {
    loop {
        let mut status: libc::c_int = 0;
        // Safety: status is a valid out-pointer; return code checked.
        let pid = unsafe { libc::waitpid(-1, &mut status, 0) };
        if pid < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if pid != workload {
            continue; // an orphan: reaped, nothing to report
        }
        if libc::WIFEXITED(status) {
            return Ok(libc::WEXITSTATUS(status));
        }
        if libc::WIFSIGNALED(status) {
            return Ok(128 + libc::WTERMSIG(status));
        }
    }
}

/// One D4 mount: create the target, then mount(2) with the mapped flags.
pub(crate) fn mount_step(m: &GuestMount) -> io::Result<()> {
    std::fs::create_dir_all(&m.target)?;
    let cstr = |s: &str| {
        CString::new(s).map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "nul byte"))
    };
    let (source, target, fstype, data) = (
        cstr(&m.source)?,
        cstr(&m.target)?,
        cstr(&m.fstype)?,
        cstr(&m.data)?,
    );
    let mut flags: libc::c_ulong = 0;
    for (on, bit) in [
        (m.flags.rdonly, libc::MS_RDONLY),
        (m.flags.nosuid, libc::MS_NOSUID),
        (m.flags.nodev, libc::MS_NODEV),
        (m.flags.noexec, libc::MS_NOEXEC),
    ] {
        if on {
            flags |= bit as libc::c_ulong;
        }
    }
    let data_ptr = if m.data.is_empty() {
        std::ptr::null()
    } else {
        data.as_ptr() as *const libc::c_void
    };
    // Safety: every pointer is a valid C string (or NULL data) for the call.
    let rc = unsafe {
        libc::mount(
            source.as_ptr(),
            target.as_ptr(),
            fstype.as_ptr(),
            flags as _,
            data_ptr,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

/// `SIOCSIFFLAGS IFF_UP|IFF_RUNNING` on `lo` (spike `guest/boot.sh:9`).
/// `struct ifreq` is 40 bytes on 64-bit Linux: a 16-byte name, then a union
/// whose `short ifr_flags` member is first.
pub(crate) fn loopback_up() -> io::Result<()> {
    #[repr(C)]
    struct IfReqFlags {
        name: [u8; 16],
        flags: libc::c_short,
        _pad: [u8; 22],
    }
    let mut req = IfReqFlags {
        name: [0; 16],
        flags: 0,
        _pad: [0; 22],
    };
    req.name[..2].copy_from_slice(b"lo");
    // Safety: a plain datagram socket for the ioctl; closed below.
    let fd = unsafe { libc::socket(libc::AF_INET, libc::SOCK_DGRAM | libc::SOCK_CLOEXEC, 0) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // Safety: req is a valid ifreq-sized buffer for both requests.
    let rc = unsafe {
        if libc::ioctl(fd, libc::SIOCGIFFLAGS as _, &mut req) != 0 {
            -1
        } else {
            req.flags |= (libc::IFF_UP | libc::IFF_RUNNING) as libc::c_short;
            libc::ioctl(fd, libc::SIOCSIFFLAGS as _, &mut req)
        }
    };
    let err = io::Error::last_os_error();
    unsafe { libc::close(fd) };
    if rc != 0 {
        return Err(err);
    }
    Ok(())
}

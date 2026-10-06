//! Control transport path.
//! unix: a `.sock` unix-domain-socket path inside the run dir.
//! windows: a named pipe whose name is derived deterministically from the run
//!          id (the run dir's file name), so client and server agree without
//!          any extra shared state. A presence sentinel file in the run dir
//!          mirrors `.sock`'s "does the endpoint exist?" check.
//! JSON wire protocol is identical on both transports.

use std::path::PathBuf;

#[cfg(unix)]
use lightr_core::{LightrError, Result};

#[cfg(unix)]
pub(super) fn ctl_sock_path(dir: &std::path::Path) -> PathBuf {
    dir.join("ctl.sock")
}

/// Longest `ctl.sock` path this host can bind, in bytes: `sun_path`'s size
/// minus its NUL terminator (macOS 104 → 103, Linux 108 → 107). std's bind
/// rejects any path of `sun_path.len()` bytes or more.
#[cfg(unix)]
pub(super) const CTL_SOCK_MAX_BYTES: usize = {
    // SAFETY: `sockaddr_un` is plain old data; all-zero bytes are a valid value.
    let addr: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    std::mem::size_of_val(&addr.sun_path) - 1
};

/// Refuse a run dir whose `ctl.sock` cannot be bound on this host. Past the
/// limit the supervisor has no control plane, so `stop`/`ps` cannot reach the
/// run. Callers run this before creating or launching anything for the run.
#[cfg(unix)]
pub(super) fn ensure_ctl_sock_fits(dir: &std::path::Path) -> Result<()> {
    check_sock_len(&ctl_sock_path(dir), CTL_SOCK_MAX_BYTES).map_err(LightrError::InvalidRef)
}

/// Windows: the control endpoint is a named pipe (`ctl_pipe_name`), which has
/// no `sun_path` limit, so nothing to refuse.
#[cfg(windows)]
pub(super) fn ensure_ctl_sock_fits(_dir: &std::path::Path) -> lightr_core::Result<()> {
    Ok(())
}

/// The length check behind `ensure_ctl_sock_fits`, with the limit injected so
/// tests can probe its boundary. Counts bytes, not chars: `sun_path` is bytes.
#[cfg(unix)]
pub(super) fn check_sock_len(
    sock: &std::path::Path,
    max: usize,
) -> std::result::Result<(), String> {
    use std::os::unix::ffi::OsStrExt;
    let len = sock.as_os_str().as_bytes().len();
    if len <= max {
        return Ok(());
    }
    Err(format!(
        "detached run control socket path is {len} bytes, over this host's {max}-byte \
         AF_UNIX limit: {}; set LIGHTR_HOME to a path at least {} bytes shorter",
        sock.display(),
        len - max
    ))
}

/// The run's bound control socket. Dropping it removes `ctl.sock`, so every
/// supervisor return path (including `?` errors after the bind) leaves no
/// stale endpoint behind. Terminal paths drop it explicitly BEFORE writing the
/// `exited` status (FIX-#76 teardown order; see `stop::supervisor_alive`).
#[cfg(unix)]
pub(super) struct CtlListener {
    pub(super) listener: std::os::unix::net::UnixListener,
    path: PathBuf,
}

#[cfg(unix)]
impl Drop for CtlListener {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

/// Bind the run's control socket (non-blocking). A failure is recorded in the
/// run dir (`stderr.log` + a terminal `exited 2` status) so `ps`/`status`/
/// `logs` show why the run never started. Supervisors call this before they
/// start any workload, so a failure leaves nothing running.
#[cfg(unix)]
pub(super) fn bind_ctl_listener(dir: &std::path::Path) -> Result<CtlListener> {
    let path = ctl_sock_path(dir);
    let bound = ensure_ctl_sock_fits(dir).and_then(|()| {
        let listener = std::os::unix::net::UnixListener::bind(&path).map_err(LightrError::Io)?;
        let ctl = CtlListener { listener, path };
        ctl.listener
            .set_nonblocking(true)
            .map_err(LightrError::Io)?;
        Ok(ctl)
    });
    bound.inspect_err(|e| record_setup_failure(dir, &format!("control socket: {e}")))
}

/// Exit code written to `status` when the supervisor fails before the workload
/// starts. It matches the `__supervise` process's own exit code for an error.
#[cfg(unix)]
pub(super) const SETUP_FAILURE_CODE: i32 = 2;

#[cfg(unix)]
fn record_setup_failure(dir: &std::path::Path, why: &str) {
    use std::io::Write;
    if let Ok(mut log) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("stderr.log"))
    {
        let _ = writeln!(log, "lightr: supervise error: {why}");
    }
    let _ = std::fs::write(dir.join("status"), format!("exited {SETUP_FAILURE_CODE}"));
}

// WIN-PATH: named-pipe address `\\.\pipe\lightr-<id>`. The id is the run dir's
// file name — the same identity the unix `.sock` lives under — so a client
// computes the identical pipe name from the same `dir`. Runtime-validatable
// only on a real Windows box.
#[cfg(windows)]
pub(super) fn ctl_pipe_name(dir: &std::path::Path) -> String {
    let id = dir
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "default".to_string());
    format!(r"\\.\pipe\lightr-{id}")
}

// Windows sentinel mirroring `ctl.sock`'s existence semantics. The named pipe
// itself is not a filesystem object pollable via `Path::exists`, so the
// supervisor touches this file once the pipe server is listening and removes
// it on exit. `ps`/`stop` test this exactly like the unix `.sock` path.
#[cfg(windows)]
pub(super) fn ctl_sock_path(dir: &std::path::Path) -> PathBuf {
    dir.join("ctl.pipe.live")
}

#[cfg(unix)]
pub(super) fn send_ctl_op(dir: &std::path::Path, op: &str) -> Option<serde_json::Value> {
    use std::io::{BufRead, BufReader, Write};
    use std::os::unix::net::UnixStream;
    use std::time::Duration;

    let sock = ctl_sock_path(dir);
    if !sock.exists() {
        return None;
    }
    let mut stream = UnixStream::connect(&sock).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(1))).ok()?;
    stream.write_all(op.as_bytes()).ok()?;
    stream.write_all(b"\n").ok()?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).ok()?;
    serde_json::from_str(line.trim()).ok()
}

// WIN-PATH: named-pipe client. Opens `\\.\pipe\lightr-<id>` with CreateFileW
// (the pipe server is a BLOCKING PIPE_TYPE_BYTE / PIPE_WAIT pipe — see
// `supervise`), wraps the handle in a std File, and exchanges the SAME
// newline-delimited JSON request/response as the unix transport. The wire
// protocol is byte-identical; only the transport differs.
// Runtime-validatable only on a real Windows box.
#[cfg(windows)]
pub(super) fn send_ctl_op(dir: &std::path::Path, op: &str) -> Option<serde_json::Value> {
    use std::fs::File;
    use std::io::{BufRead, BufReader, Write};
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::{GENERIC_READ, GENERIC_WRITE, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{CreateFileW, OPEN_EXISTING};

    // Mirror the unix `sock.exists()` guard: if the supervisor's live sentinel
    // is absent, there is no endpoint to talk to.
    let sentinel = ctl_sock_path(dir);
    if !sentinel.exists() {
        return None;
    }

    let name = ctl_pipe_name(dir);
    // Build a NUL-terminated wide string for CreateFileW.
    let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();

    // dwShareMode=0, no security attrs, no extra flags (FILE_FLAGS_AND_ATTRIBUTES
    // is a u32 alias in windows-sys 0.59 — pass 0), no template handle.
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            GENERIC_READ | GENERIC_WRITE,
            0,
            std::ptr::null(),
            OPEN_EXISTING,
            0,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return None;
    }

    // SAFETY: handle is a valid, owned pipe handle; File takes ownership and
    // closes it on drop.
    let file = unsafe { File::from_raw_handle(handle as *mut _) };
    // We need two independent halves (write the request, then buffered-read the
    // reply). try_clone duplicates the underlying handle.
    let mut writer = file.try_clone().ok()?;
    writer.write_all(op.as_bytes()).ok()?;
    writer.write_all(b"\n").ok()?;
    writer.flush().ok()?;

    let mut reader = BufReader::new(file);
    let mut line = String::new();
    reader.read_line(&mut line).ok()?;
    serde_json::from_str(line.trim()).ok()
}

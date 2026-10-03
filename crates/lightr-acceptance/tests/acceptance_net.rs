//! Networking Phase 1 acceptance — `lightr run [-d] -p HOST:CONTAINER`.
//!
//! Proves the daemonless userspace forward-proxy: a detached published run is
//! reachable on the host port (forwarded to 127.0.0.1:CONTAINER where the
//! server listens), and `lightr stop` tears the forwarder down with the run.
//!
//! The server is `python3 -m http.server` (present on macOS + Linux CI). If
//! `python3` is not on PATH the reachability test SKIPS gracefully (prints why,
//! passes) — a missing server binary must not fail the suite.
//!
//! Gate: cargo fmt --check · cargo clippy -p lightr-acceptance --all-targets
//!       -D warnings · cargo test -p lightr-acceptance.

#[path = "common/mod.rs"]
#[allow(dead_code)] // shared helpers; this suite uses only `lightr_cmd`
mod common;

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::time::{Duration, Instant};

use assert_cmd::cargo::cargo_bin;
use common::lightr_cmd;
use tempfile::TempDir;

#[path = "acceptance_net/probe_tests.rs"]
mod probe_tests;

#[cfg(unix)]
#[path = "acceptance_net/reserved_target.rs"]
mod reserved_target;

// ---------------------------------------------------------------------------
// Guard: stop a detached run on Drop so no process/forwarder is leaked.
// ---------------------------------------------------------------------------
struct RunGuard {
    id: String,
    home: PathBuf,
}

impl Drop for RunGuard {
    fn drop(&mut self) {
        let _ = lightr_cmd(&self.home)
            .args(["stop", &self.id, "--grace", "1"])
            .output();
    }
}

/// Parse `id=<id>` from stdout.
fn parse_id_from_stdout(stdout: &[u8]) -> String {
    let text = String::from_utf8_lossy(stdout);
    // Detached run prints the bare container id (Docker parity, #77); tolerate a
    // legacy `id=` prefix too. Take the last non-empty stdout line.
    for line in text.lines().rev() {
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        return t.strip_prefix("id=").unwrap_or(t).to_owned();
    }
    panic!("could not find a container id in stdout:\n{text}");
}

/// True if `python3` is on PATH (probe `python3 --version`).
fn python3_available() -> bool {
    std::process::Command::new("python3")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Select distinct localhost ports while both listeners are bound.
/// The listeners are released before return; the ports are not reserved afterward.
fn free_port_pair() -> (u16, u16) {
    let host = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral host port");
    let container = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral container port");
    (
        host.local_addr().unwrap().port(),
        container.local_addr().unwrap().port(),
    )
}

#[test]
fn net_port_pair_selects_distinct_nonzero_ports() {
    for _ in 0..16 {
        let (host_port, container_port) = free_port_pair();
        assert_ne!(host_port, 0, "host port must be selected by the OS");
        assert_ne!(
            container_port, 0,
            "container port must be selected by the OS"
        );
        assert_ne!(
            host_port, container_port,
            "published ports must be distinct"
        );
    }
}

/// Try one HTTP GET / through `127.0.0.1:port`; return the response bytes on
/// success (connect + write + any bytes read back), else None.
fn http_probe(port: u16, deadline: Instant) -> Option<Vec<u8>> {
    let remaining = deadline.checked_duration_since(Instant::now())?;
    let address = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, remaining).ok()?;
    stream
        .set_write_timeout(Some(deadline.checked_duration_since(Instant::now())?))
        .ok()?;
    stream
        .write_all(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        .ok()?;
    stream.flush().ok()?;
    let mut buf = Vec::new();
    // Read whatever the server sends before it closes / times out.
    let mut chunk = [0u8; 4096];
    while let Some(remaining) = deadline.checked_duration_since(Instant::now()) {
        stream.set_read_timeout(Some(remaining)).ok()?;
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                buf.extend_from_slice(&chunk[..n]);
                if buf.len() > 16 {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    if buf.is_empty() {
        None
    } else {
        Some(buf)
    }
}

/// Poll `http_probe` up to `timeout`; return the first response that arrives.
fn poll_http(port: u16, timeout: Duration) -> Option<Vec<u8>> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Some(resp) = http_probe(port, deadline) {
            return Some(resp);
        }
        std::thread::sleep(
            Duration::from_millis(100).min(deadline.saturating_duration_since(Instant::now())),
        );
    }
    None
}

/// True once `127.0.0.1:port` refuses connections (forwarder gone).
fn port_closed(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_err() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

// ---------------------------------------------------------------------------
// Reachability + teardown of a detached published run.
// ---------------------------------------------------------------------------
#[test]
fn net_published_run_is_reachable_then_torn_down() {
    if !python3_available() {
        eprintln!(
            "SKIP net_published_run_is_reachable_then_torn_down: python3 not on PATH \
             (cannot start a real HTTP server). Phase-1 forwarder wiring is still \
             exercised by the lightr-run portforward unit tests."
        );
        return;
    }

    let home = TempDir::new().unwrap();
    let ws = TempDir::new().unwrap();

    let (host_port, container_port) = free_port_pair();

    // Start a detached published run: server binds 127.0.0.1:<container_port>,
    // forwarder publishes 127.0.0.1:<host_port> → it.
    let hp = host_port.to_string();
    let cp = container_port.to_string();
    let publish = format!("{host_port}:{container_port}");
    let out = lightr_cmd(home.path())
        .args([
            "run",
            "-d",
            "-p",
            &publish,
            "--dir",
            ws.path().to_str().unwrap(),
            "--",
            "python3",
            "-m",
            "http.server",
            &cp,
            "--bind",
            "127.0.0.1",
        ])
        .output()
        .expect("run -d -p must launch");
    assert_eq!(
        out.status.code().unwrap_or(-1),
        0,
        "run -d -p must exit 0; stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let id = parse_id_from_stdout(&out.stdout);
    let _guard = RunGuard {
        id: id.clone(),
        home: home.path().to_path_buf(),
    };

    // Reachability: an HTTP response must come back THROUGH the forwarder.
    let resp = poll_http(host_port, Duration::from_secs(8));
    assert!(
        resp.is_some(),
        "no HTTP response on host port {hp} within 8s (forwarder→127.0.0.1:{cp})"
    );
    let resp = resp.unwrap();
    let text = String::from_utf8_lossy(&resp);
    assert!(
        text.starts_with("HTTP/"),
        "response through forwarder must be HTTP, got: {:?}",
        &text.chars().take(40).collect::<String>()
    );

    // Teardown: stop the run, then the host port must stop serving.
    let stop_out = lightr_cmd(home.path())
        .args(["stop", &id, "--grace", "2"])
        .output()
        .expect("stop must launch");
    let _ = stop_out.status.code();

    assert!(
        port_closed(host_port, Duration::from_secs(5)),
        "host port {hp} must stop serving after stop (forwarder dropped)"
    );
}

// ---------------------------------------------------------------------------
// Foreground run: HTTP reaches host port while workload lives, then the port closes.
// ---------------------------------------------------------------------------
#[test]
fn net_foreground_published_run_is_reachable_then_torn_down() {
    if !python3_available() {
        eprintln!(
            "SKIP net_foreground_published_run_is_reachable_then_torn_down: python3 not on PATH"
        );
        return;
    }

    let home = TempDir::new().unwrap();
    let ws = TempDir::new().unwrap();
    #[cfg(unix)]
    let (mut command, reservation, host_port, container_port) =
        reserved_target::prepare(&cargo_bin("lightr"), ws.path());
    #[cfg(not(unix))]
    let (host_port, container_port) = free_port_pair();
    #[cfg(not(unix))]
    let publish = format!("127.0.0.1:{host_port}:{container_port}");
    #[cfg(not(unix))]
    let cp = container_port.to_string();
    // Serve exactly one request, then exit normally. This proves normal workload
    // exit drops the foreground-owned forwarder without leaving a child behind.
    #[cfg(not(unix))]
    let server = format!(
        "from http.server import SimpleHTTPRequestHandler; from socketserver import TCPServer; \
         server = TCPServer(('127.0.0.1', {container_port}), SimpleHTTPRequestHandler); \
         server.timeout = 5; server.handle_request()"
    );
    #[cfg(not(unix))]
    let mut command = {
        let mut command = std::process::Command::new(cargo_bin("lightr"));
        command.args([
            "run",
            "--explain",
            "-p",
            &publish,
            "--dir",
            ws.path().to_str().unwrap(),
            "--",
            "python3",
            "-c",
            &server,
            &cp,
        ]);
        command
    };
    command
        .env("LIGHTR_HOME", home.path())
        .env_remove("HTTP_PROXY")
        .env_remove("HTTPS_PROXY")
        .env_remove("ALL_PROXY")
        .env_remove("http_proxy")
        .env_remove("https_proxy")
        .env_remove("all_proxy")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    #[cfg(unix)]
    drop(reservation); // only host is rebound by lightr; target remains owned through stdin/exec
    let mut child = command.spawn().expect("foreground run -p must launch");

    let response = poll_http(host_port, Duration::from_secs(8));
    let failure = if response.is_none() {
        if let Some(status) = child
            .try_wait()
            .expect("foreground run status must be readable")
        {
            let output = child.wait_with_output().expect("exited workload output");
            panic!(
                "foreground host port {host_port}, target {container_port}: exited {status}; stdout={:?}; stderr={:?}",
                String::from_utf8_lossy(&output.stdout),
                String::from_utf8_lossy(&output.stderr)
            );
        }
        "still running".to_string()
    } else {
        String::new()
    };
    assert_eq!(
        response.as_deref().map(|body| body.starts_with(b"HTTP/")),
        Some(true),
        "foreground host port {host_port} must serve HTTP through forwarder ({failure})"
    );

    let status = child.wait().expect("foreground run must exit");
    assert!(
        status.success(),
        "one-request foreground workload must exit successfully"
    );
    assert!(
        port_closed(host_port, Duration::from_secs(5)),
        "foreground host port {host_port} must close when workload exits"
    );
}

// ---------------------------------------------------------------------------
// Negative: malformed and unavailable foreground publishes fail closed.
// ---------------------------------------------------------------------------
#[test]
fn net_foreground_publish_invalid_or_unavailable_target_fails_closed() {
    let home = TempDir::new().unwrap();
    let malformed = lightr_cmd(home.path())
        .args(["run", "-p", "bad", "--", "true"])
        .output()
        .expect("malformed foreground publish must launch");
    assert_eq!(malformed.status.code(), Some(2));

    let held = std::net::TcpListener::bind("127.0.0.1:0").expect("hold host port");
    let host_port = held.local_addr().unwrap().port().to_string();
    let publish = format!("127.0.0.1:{host_port}:12345");
    let unavailable = lightr_cmd(home.path())
        .args(["run", "-p", &publish, "--", "true"])
        .output()
        .expect("unavailable foreground publish must launch");
    assert_ne!(unavailable.status.code(), Some(0));
    assert!(
        String::from_utf8_lossy(&unavailable.stderr).contains("Address already in use"),
        "occupied host target must report bind failure: {}",
        String::from_utf8_lossy(&unavailable.stderr)
    );
}

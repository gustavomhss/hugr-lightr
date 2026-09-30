//! A25, A25b acceptance tests (docker compat + exit-code law).

use crate::common::lightr_cmd;
use std::fs;
use std::io::{self, Read, Write};
use std::net::TcpListener;
use std::thread;
use std::time::{Duration, Instant};
use tempfile::TempDir;

// ─────────────────────────────────────────────────────────────────────────────
// A25 — docker compat
//
// `lightr docker build -t @t/d <ctx>` → exit 0 + stderr contains "lightr build"
// `lightr docker images`               → lists @t/d
// `lightr docker frobnicate`           → exit 2 + stderr contains "unsupported"
//                                        and mentions supported verbs
// ─────────────────────────────────────────────────────────────────────────────

#[test]
fn a25_docker_compat() {
    let home = TempDir::new().unwrap();
    let ctx = TempDir::new().unwrap();

    // Minimal Dockerfile for the docker build test.
    fs::write(
        ctx.path().join("Dockerfile"),
        "FROM scratch\nCOPY data.txt /data.txt\n",
    )
    .unwrap();
    fs::write(ctx.path().join("data.txt"), b"a25").unwrap();

    // ── docker build → exit 0 + stderr transparency note ───────────────────
    let build_out = lightr_cmd(home.path())
        .args([
            "docker",
            "build",
            "-t",
            "@t/d",
            ctx.path().to_str().unwrap(),
        ])
        .output()
        .expect("docker build must not fail to spawn");
    assert_eq!(
        build_out.status.code().unwrap_or(-1),
        0,
        "docker build must exit 0; stderr:\n{}",
        String::from_utf8_lossy(&build_out.stderr)
    );
    // Transparency note: stderr must say it ran "lightr build" (per §4).
    let build_stderr = String::from_utf8_lossy(&build_out.stderr).to_lowercase();
    assert!(
        build_stderr.contains("lightr build") || build_stderr.contains("lightr-build"),
        "docker build stderr must mention 'lightr build' (transparency note); got:\n{}",
        String::from_utf8_lossy(&build_out.stderr)
    );

    // ── docker images → lists @t/d ──────────────────────────────────────────
    let images_out = lightr_cmd(home.path())
        .args(["docker", "images"])
        .output()
        .expect("docker images must not fail to spawn");
    assert_eq!(
        images_out.status.code().unwrap_or(-1),
        0,
        "docker images must exit 0; stderr:\n{}",
        String::from_utf8_lossy(&images_out.stderr)
    );
    let images_stdout = String::from_utf8_lossy(&images_out.stdout);
    assert!(
        images_stdout.contains("@t/d") || images_stdout.contains("t/d"),
        "docker images must list @t/d after docker build; got:\n{}",
        images_stdout
    );

    // ── docker frobnicate → exit 2 + "unsupported" + supported list ─────────
    let frob_out = lightr_cmd(home.path())
        .args(["docker", "frobnicate"])
        .output()
        .expect("docker frobnicate must not fail to spawn");
    assert_eq!(
        frob_out.status.code().unwrap_or(-1),
        2,
        "docker frobnicate must exit 2 (unsupported subcommand)"
    );
    let frob_stderr = String::from_utf8_lossy(&frob_out.stderr).to_lowercase();
    assert!(
        frob_stderr.contains("unsupported"),
        "docker frobnicate stderr must contain 'unsupported'; got:\n{}",
        String::from_utf8_lossy(&frob_out.stderr)
    );
    // Must name at least one of the supported verbs.
    let mentions_supported = frob_stderr.contains("build")
        || frob_stderr.contains("run")
        || frob_stderr.contains("pull")
        || frob_stderr.contains("images")
        || frob_stderr.contains("ps")
        || frob_stderr.contains("compose");
    assert!(
        mentions_supported,
        "docker frobnicate stderr must mention supported verbs (build|run|pull|images|ps|compose); got:\n{}",
        String::from_utf8_lossy(&frob_out.stderr)
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// A25b — docker subcommand exit-code law
//
// `lightr docker ps` → must exit 0 (translates to `ps`).
// `lightr docker pull localhost:<port>/a25:missing` → registry connection
// error: exit 1 with a diagnostic, within the exact 0|1 law (never 2).
// Frozen A25 does not pin alpine (build-spec-r3 §6). This is an offline
// exit-mapping witness; the external R1 pull integration remains separate.
// ─────────────────────────────────────────────────────────────────────────────

/// Pull currently uses HTTPS even for localhost (oci/pull.rs). Reject its
/// ClientHello with a fatal handshake_failure alert, without certificates or
/// public registries. This witnesses a transport error, not an HTTP 404.
fn reject_registry_tls(listener: TcpListener) -> io::Result<Vec<u8>> {
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut stream = loop {
        match listener.accept() {
            Ok((stream, _)) => break stream,
            Err(e) if e.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(10));
            }
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "docker pull never contacted the loopback registry",
                ));
            }
            Err(e) => return Err(e),
        }
    };
    // Darwin accept inherits O_NONBLOCK; timeouts need a blocking stream.
    stream.set_nonblocking(false)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let mut header = [0; 5];
    stream.read_exact(&mut header)?;
    let len = u16::from_be_bytes([header[3], header[4]]) as usize;
    if len == 0 || len > 16384 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "expected a bounded TLS ClientHello record",
        ));
    }
    let mut hello = header.to_vec();
    hello.resize(5 + len, 0);
    stream.read_exact(&mut hello[5..])?;
    // TLS alert record: TLS 1.2 record version, fatal, handshake_failure (40).
    stream.write_all(&[21, 3, 3, 0, 2, 2, 40])?;
    Ok(hello)
}

#[test]
fn a25b_docker_ps_and_pull_exit_law() {
    let home = TempDir::new().unwrap();

    // docker ps → translates to `lightr ps` → exit 0 always.
    let ps_out = lightr_cmd(home.path())
        .args(["docker", "ps"])
        .output()
        .expect("docker ps must not fail to spawn");
    assert_eq!(
        ps_out.status.code().unwrap_or(-1),
        0,
        "docker ps must exit 0 (translates to lightr ps); stderr:\n{}",
        String::from_utf8_lossy(&ps_out.stderr)
    );

    // Bound ephemeral listener is readiness proof; no connect-to-probe race.
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let port = listener.local_addr().unwrap().port();
    let image = format!("localhost:{port}/a25:missing");
    let pull_out = thread::scope(|scope| {
        // Scoped join also runs on panic; accept/read/write are all bounded.
        let server = scope.spawn(move || reject_registry_tls(listener));
        let output = lightr_cmd(home.path())
            .env("DOCKER_CONFIG", home.path())
            .env_remove("LIGHTR_REGISTRY_AUTH")
            .args(["docker", "pull", &image])
            .timeout(Duration::from_secs(30))
            .output()
            .expect("docker pull must not fail to spawn");
        let hello = server
            .join()
            .expect("loopback registry thread must not panic")
            .expect("real docker pull must contact the loopback registry");
        assert!(
            hello.starts_with(&[22, 3]) && hello[5] == 1,
            "registry must receive a TLS ClientHello from real docker pull; got: {hello:?}"
        );
        eprintln!(
            "loopback registry received TLS ClientHello ({} bytes) from real docker pull",
            hello.len()
        );
        output
    });
    let pull_code = pull_out.status.code().unwrap_or(-1);
    assert!(
        pull_code == 0 || pull_code == 1,
        "docker pull must exit 0 or 1; got exit={pull_code} stderr:\n{}",
        String::from_utf8_lossy(&pull_out.stderr)
    );
    assert_ne!(
        pull_code, 2,
        "docker pull must NEVER exit 2 for a valid image ref"
    );
    assert_eq!(
        pull_code,
        1,
        "docker pull must map the loopback registry failure to exit 1; stderr:\n{}",
        String::from_utf8_lossy(&pull_out.stderr)
    );
    let pull_stderr = String::from_utf8_lossy(&pull_out.stderr);
    assert!(
        pull_stderr.contains("lightr docker: → lightr oci pull")
            && pull_stderr.contains(&image)
            && pull_stderr.contains("lightr: ")
            && pull_stderr.contains("HandshakeFailure"),
        "docker pull must diagnose the fixture's fatal TLS alert; got:\n{pull_stderr}"
    );
}

//! Unix fixture: keep target ownership through exec instead of releasing/rebinding.
use super::*;
use std::os::fd::OwnedFd;

pub(super) fn prepare(
    binary: &std::path::Path,
    workspace: &std::path::Path,
) -> (std::process::Command, TcpListener, u16, u16) {
    let target = TcpListener::bind("127.0.0.1:0").expect("reserve target listener");
    let host = TcpListener::bind("127.0.0.1:0").expect("reserve distinct host listener");
    let target_port = target.local_addr().unwrap().port();
    let host_port = host.local_addr().unwrap().port();
    assert_ne!(host_port, target_port);
    let launcher = r#"
import os, socket, sys
listener = socket.socket(fileno=os.dup(0))
assert listener.getsockname() == ('127.0.0.1', int(sys.argv[3]))
fd = listener.fileno()
os.set_inheritable(fd, True)
server = (
    'from http.server import SimpleHTTPRequestHandler; from socketserver import TCPServer; import socket; '
    'server=TCPServer(("127.0.0.1",'+sys.argv[3]+'),SimpleHTTPRequestHandler,bind_and_activate=False); '
    'server.socket.close(); server.socket=socket.socket(fileno='+str(fd)+'); '
    'server.server_address=server.socket.getsockname(); server.timeout=5; server.handle_request()'
)
# Replace launcher with the real CLI: Rust still observes lightr's PID/status.
os.execv(sys.argv[1], [sys.argv[1], 'run', '--explain', '-p', sys.argv[2], '--dir', sys.argv[4],
                    '--', sys.executable, '-c', server])
"#;
    let fd: OwnedFd = target.into();
    let mut command = std::process::Command::new("python3");
    command.stdin(std::process::Stdio::from(fd)).args([
        "-c",
        launcher,
        binary.to_str().unwrap(),
        &format!("127.0.0.1:{host_port}:{target_port}"),
        &target_port.to_string(),
        workspace.to_str().unwrap(),
    ]);
    (command, host, host_port, target_port)
}

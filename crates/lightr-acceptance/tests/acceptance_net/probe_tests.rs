//! Real socket controls for the one-request foreground workload's HTTP probe.
use super::*;

#[cfg(unix)]
#[test]
fn foreground_target_stays_reserved_until_spawn() {
    let (command, host, host_port, target_port) = reserved_target::prepare(
        std::path::Path::new("/unused/control"),
        std::path::Path::new("."),
    );
    for port in [host_port, target_port] {
        let error =
            TcpListener::bind(("127.0.0.1", port)).expect_err("fixture port lost ownership");
        assert_eq!(error.kind(), std::io::ErrorKind::AddrInUse);
    }
    drop(command);
    assert_eq!(host.local_addr().unwrap().port(), host_port);
}

fn accept_before(listener: &TcpListener, deadline: Instant) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    loop {
        match listener.accept() {
            Ok((stream, _)) => {
                stream.set_nonblocking(false).unwrap();
                return stream;
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(
                    Instant::now() < deadline,
                    "control accept deadline exceeded"
                );
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(error) => panic!("control accept failed: {error}"),
        }
    }
}

#[test]
fn one_request_response_keeps_the_overall_poll_budget() {
    for delay in [Duration::ZERO, Duration::from_millis(1100)] {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let budget = Duration::from_secs(3);
        let start = Instant::now();
        let server = std::thread::spawn(move || {
            let mut stream = accept_before(&listener, start + budget);
            // Exactly one request: a retry cannot replace the abandoned socket.
            drop(listener);
            stream.set_read_timeout(Some(budget)).unwrap();
            stream.set_write_timeout(Some(budget)).unwrap();
            let mut request = [0; 35];
            stream.read_exact(&mut request).unwrap();
            assert_eq!(&request, b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n");
            std::thread::sleep(delay);
            let _ = stream.write_all(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok");
            start.elapsed()
        });
        let response = poll_http(port, budget);
        let served_at = server.join().unwrap();
        assert!(
            served_at < budget,
            "control responded after the overall budget"
        );
        assert_eq!(
            response.as_deref().map(|bytes| bytes.starts_with(b"HTTP/")),
            Some(true),
            "one-request response delayed {delay:?} was lost inside {budget:?} budget"
        );
    }
}

#[test]
fn silent_one_request_peer_does_not_extend_poll_deadline() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let start = Instant::now();
    let server = std::thread::spawn(move || {
        let mut stream = accept_before(&listener, start + Duration::from_secs(2));
        drop(listener);
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let mut request = [0; 35];
        stream.read_exact(&mut request).unwrap();
        // A silent server observes the client close when its 200ms budget expires,
        // before the old unrelated 800ms per-read timeout could do so.
        stream
            .set_read_timeout(Some(Duration::from_millis(600)))
            .unwrap();
        stream.read(&mut [0])
    });
    assert!(poll_http(port, Duration::from_millis(200)).is_none());
    assert_eq!(
        server.join().unwrap().unwrap(),
        0,
        "deadline did not close client"
    );
}

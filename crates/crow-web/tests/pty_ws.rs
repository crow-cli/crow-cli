//! End to end over a real socket: the shipped `crow-web` binary, a shell per
//! connection, and the kernel's own `/proc` as the witness.
//!
//! `src/pty.rs` unit-tests the session (input, output, resize, reap, drop).
//! This is the tier above it — the shape xterm.js will use — so it asserts the
//! two things only a real socket can prove: bytes survive the wire in both
//! directions, and a closed tab takes its process with it.
mod common;

use std::path::PathBuf;
use std::time::Duration;

use common::Server;
use futures::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio_tungstenite::tungstenite::Message;

type WsStream =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

/// `/bin/sh`, not `$SHELL`: these tests type into the terminal and read back
/// what arrives, so no rc files and no prompt themes.
fn start(name: &str) -> Server {
    common::spawn(name, &["--shell", "/bin/sh"])
}

/// The url a terminal tab connects to, at the size its pane already has.
fn pty_url(server: &Server, cols: u16, rows: u16) -> String {
    format!("{}?cols={cols}&rows={rows}", server.ws("/pty"))
}

/// The kernel's own witness that a shell exists — no `ps` parsing.
fn alive(pid: u32) -> bool {
    PathBuf::from(format!("/proc/{pid}")).exists()
}

async fn gone(pid: u32) -> bool {
    for _ in 0..150 {
        if !alive(pid) {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    false
}

/// One connected terminal tab.
struct Term {
    ws: WsStream,
    /// Everything the pty has said so far, decoded lossily.
    seen: String,
}

impl Term {
    async fn connect(url: &str) -> Self {
        let (ws, response) = tokio_tungstenite::connect_async(url)
            .await
            .expect("connect to /pty");
        assert_eq!(response.status(), 101);
        let mut term = Self {
            ws,
            seen: String::new(),
        };
        let hello = term.next_json().await;
        assert_eq!(hello["type"], "hello", "{hello}");
        term.seen.clear();
        term
    }

    /// The next text frame, parsed. Binary frames are collected on the way.
    async fn next_json(&mut self) -> Value {
        loop {
            match self.next_raw().await {
                Message::Text(text) => return serde_json::from_str(&text).expect("json control"),
                Message::Binary(bytes) => self.seen.push_str(&String::from_utf8_lossy(&bytes)),
                other => panic!("expected a text frame, got {other:?}"),
            }
        }
    }

    async fn next_raw(&mut self) -> Message {
        match tokio::time::timeout(Duration::from_secs(20), self.ws.next())
            .await
            .expect("the terminal went quiet")
        {
            Some(Ok(frame)) => frame,
            Some(Err(e)) => panic!("websocket error: {e}"),
            None => panic!("the server closed the socket"),
        }
    }

    /// Types into the terminal, as xterm.js does: bytes, not JSON.
    async fn send(&mut self, line: &str) {
        self.ws
            .send(Message::Binary(line.as_bytes().to_vec().into()))
            .await
            .expect("send input");
    }

    async fn resize(&mut self, cols: u16, rows: u16) {
        self.ws
            .send(Message::Text(
                json!({"type": "resize", "cols": cols, "rows": rows})
                    .to_string()
                    .into(),
            ))
            .await
            .expect("send resize");
    }

    /// Reads until the pty has said `needle`, and fails with the transcript.
    async fn expect(&mut self, needle: &str) {
        let from = self.seen.len();
        loop {
            if self.seen[from..].contains(needle) {
                return;
            }
            match self.next_raw().await {
                Message::Binary(bytes) => self.seen.push_str(&String::from_utf8_lossy(&bytes)),
                Message::Text(text) => {
                    panic!("unexpected control frame while waiting for {needle:?}: {text}")
                }
                other => panic!("expected bytes, got {other:?}"),
            }
        }
    }
}

#[tokio::test]
async fn a_terminal_tab_drives_a_real_shell_and_dies_with_it() {
    let server = start("tab");
    let url = pty_url(&server, 80, 24);
    let (ws, _) = tokio_tungstenite::connect_async(&url)
        .await
        .expect("connect to /pty");
    let mut term = Term {
        ws,
        seen: String::new(),
    };
    let hello = term.next_json().await;
    assert_eq!(hello["type"], "hello", "{hello}");
    assert_eq!(hello["cols"], json!(80));
    assert_eq!(hello["rows"], json!(24));
    let pid = hello["pid"].as_u64().expect("a pid") as u32;
    assert!(alive(pid), "the shell is a real process");

    // Input goes in as bytes and comes back as bytes, echoed by the pty.
    term.send("echo crow-pty-hi\r").await;
    term.expect("crow-pty-hi").await;

    // The shell starts in the served root and sees a real tty.
    term.send("pwd\r").await;
    term.expect(server.root.canonicalize().unwrap().to_str().unwrap())
        .await;
    term.send("test -t 1 && echo crow-pty-isatty\r").await;
    term.expect("crow-pty-isatty").await;

    // The size the url asked for is the size the kernel reports.
    term.send("stty size\r").await;
    term.expect("24 80").await;

    // A drag of the pane divider, as the browser will send it.
    term.resize(132, 43).await;
    term.send("stty size\r").await;
    term.expect("43 132").await;

    // Closing the tab kills the shell: no orphan holding a pty open.
    term.ws.close(None).await.expect("close");
    drop(term);
    assert!(gone(pid).await, "pid {pid} survived its socket");
}

#[tokio::test]
async fn two_tabs_are_two_independent_shells() {
    let server = start("tabs");
    let mut a = Term::connect(&pty_url(&server, 80, 24)).await;
    let mut b = Term::connect(&pty_url(&server, 80, 24)).await;

    a.send("echo only-in-a\r").await;
    a.expect("only-in-a").await;
    b.send("echo only-in-b\r").await;
    b.expect("only-in-b").await;
    assert!(
        !a.seen.contains("only-in-b"),
        "tab A heard tab B: {:?}",
        a.seen
    );
    assert!(
        !b.seen.contains("only-in-a"),
        "tab B heard tab A: {:?}",
        b.seen
    );

    // A resize in one tab is not a resize in the other.
    a.resize(100, 30).await;
    a.send("stty size\r").await;
    a.expect("30 100").await;
    b.send("stty size\r").await;
    b.expect("24 80").await;
}

#[tokio::test]
async fn a_shell_that_exits_reports_its_code_and_closes() {
    let server = start("exit");
    let mut term = Term::connect(&pty_url(&server, 80, 24)).await;
    term.send("exit 7\r").await;
    let exit = term.next_json().await;
    assert_eq!(exit["type"], "exit", "{exit}");
    assert_eq!(exit["code"], json!(7), "{exit}");
    assert!(exit["signal"].is_null(), "{exit}");
}

#[tokio::test]
async fn pty_refuses_a_foreign_origin() {
    let server = start("origin");
    let request = {
        use tokio_tungstenite::tungstenite::client::IntoClientRequest;
        let url = pty_url(&server, 80, 24);
        let mut request = url
            .as_str()
            .into_client_request()
            .expect("handshake request");
        request.headers_mut().insert(
            axum::http::header::ORIGIN,
            axum::http::HeaderValue::from_static("https://evil.example"),
        );
        request
    };
    let err = tokio_tungstenite::connect_async(request)
        .await
        .expect_err("a website must not get a shell");
    match err {
        tokio_tungstenite::tungstenite::Error::Http(response) => {
            assert_eq!(response.status(), 403, "{response:?}")
        }
        other => panic!("expected an HTTP refusal, got {other:?}"),
    }
}

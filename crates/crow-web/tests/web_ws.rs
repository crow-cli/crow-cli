//! The embedded SPA and the `/acp` proxy, over real sockets.
//!
//! The static half speaks plain HTTP over a `TcpStream` — there is no http
//! client in this crate's dependencies and a GET is three lines. The proxy
//! half stands the agent up as a ws echo server on a spare port and checks
//! that what goes in is exactly what comes out, text and binary alike.
use futures::{SinkExt, StreamExt};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio_tungstenite::tungstenite::Message;

mod common;

/// One GET, answered whole: the status line plus the body.
async fn http_get(port: u16, path: &str) -> (String, String) {
    let mut stream = tokio::net::TcpStream::connect(("127.0.0.1", port))
        .await
        .expect("connect");
    stream
        .write_all(
            format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                .as_bytes(),
        )
        .await
        .expect("write request");
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).await.expect("read response");
    let raw = String::from_utf8_lossy(&raw).into_owned();
    let (head, body) = raw.split_once("\r\n\r\n").expect("head then body");
    (
        head.lines().next().unwrap_or_default().to_string(),
        body.to_string(),
    )
}

/// A ws echo server: the agent's http endpoint, minus the agent.
async fn echo_upstream() -> u16 {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let port = listener.local_addr().expect("addr").port();
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(async move {
                let Ok(mut socket) = tokio_tungstenite::accept_async(stream).await else {
                    return;
                };
                while let Some(Ok(frame)) = socket.next().await {
                    if socket.send(frame).await.is_err() {
                        break;
                    }
                }
            });
        }
    });
    port
}

#[tokio::test]
async fn the_binary_serves_the_shell_and_falls_back_for_client_routes() {
    let server = common::spawn("web-static", &[]);
    let (status, body) = http_get(server.port, "/").await;
    assert!(status.contains("200"), "{status}");
    assert!(body.contains("<div id=\"root\">"), "not the shell: {body}");

    let (status, body) = http_get(server.port, "/threads/42").await;
    assert!(status.contains("200"), "{status}");
    assert!(
        body.contains("<div id=\"root\">"),
        "no SPA fallback: {body}"
    );

    let (status, _) = http_get(server.port, "/../etc/passwd").await;
    assert!(status.contains("400"), "{status}");
}

#[tokio::test]
async fn acp_frames_pass_through_untouched() {
    let upstream = echo_upstream().await;
    let url = format!("ws://127.0.0.1:{upstream}/acp");
    let server = common::spawn("web-acp", &["--acp-url", &url]);

    let (mut client, _) = tokio_tungstenite::connect_async(server.ws("/acp"))
        .await
        .expect("connect /acp");
    client
        .send(Message::Text("initialize please".into()))
        .await
        .expect("send text");
    match client.next().await.expect("frame").expect("ok") {
        Message::Text(text) => assert_eq!(text.as_str(), "initialize please"),
        other => panic!("text came back as {other:?}"),
    }
    client
        .send(Message::Binary(vec![1, 2, 3].into()))
        .await
        .expect("send binary");
    match client.next().await.expect("frame").expect("ok") {
        Message::Binary(bytes) => assert_eq!(bytes.to_vec(), vec![1, 2, 3]),
        other => panic!("binary came back as {other:?}"),
    }
}

#[tokio::test]
async fn a_dead_upstream_closes_the_client_socket() {
    // A port nothing listens on: the proxy has nowhere to go, and the honest
    // answer is a closed socket, not a hung one.
    let dead = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind")
        .local_addr()
        .expect("addr")
        .port();
    let server = common::spawn(
        "web-acp-dead",
        &["--acp-url", &format!("ws://127.0.0.1:{dead}/acp")],
    );
    let (mut client, _) = tokio_tungstenite::connect_async(server.ws("/acp"))
        .await
        .expect("connect /acp");
    client.send(Message::Text("anyone home".into())).await.ok();
    match client.next().await {
        None => {}
        Some(Err(_)) => {}
        Some(Ok(frame)) => panic!("a dead upstream answered: {frame:?}"),
    }
}

#[tokio::test]
async fn a_foreign_origin_is_refused_on_acp_too() {
    let upstream = echo_upstream().await;
    let server = common::spawn(
        "web-acp-origin",
        &["--acp-url", &format!("ws://127.0.0.1:{upstream}/acp")],
    );
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    let mut request = server.ws("/acp").into_client_request().expect("request");
    request
        .headers_mut()
        .insert("Origin", "https://evil.example".parse().expect("header"));
    let err = tokio_tungstenite::connect_async(request).await;
    assert!(err.is_err(), "a foreign origin got a socket");
}

//! The embedded web client and the `/acp` proxy.
//!
//! The SPA is compiled into the binary, so `crow-web` is one executable and
//! the browser sees one origin: `/`, `/fs`, `/pty` and `/acp` all answer from
//! the same port, and the loopback-Origin rule in `ws` covers the lot. With
//! the `dev-web` feature the same tree is read from disk instead, so a
//! `vite build --watch` in `packages/chat` lands without a rust rebuild.
//!
//! `/acp` is a frame-faithful proxy to the agent's own http server: the
//! browser talks to us, we talk to `ws://127.0.0.1:2769/acp`, and neither
//! side sees anything but its own frames. Text stays text and binary stays
//! binary because ACP is JSON-RPC over text and a proxy that re-encodes is a
//! proxy that corrupts.
use std::path::{Component, Path};

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::http::{header, HeaderMap, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use futures::{SinkExt, StreamExt};

/// Where the built SPA lives when `dev-web` reads it from disk instead of
/// from the binary. Anchored to the manifest so the cwd does not matter.
#[cfg(feature = "dev-web")]
const DIST: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../packages/chat/dist");

#[cfg(not(feature = "dev-web"))]
mod embedded {
    use rust_embed::RustEmbed;

    #[derive(RustEmbed)]
    #[folder = "../../packages/chat/dist/"]
    pub struct Assets;
}

#[derive(Clone)]
pub struct Config {
    acp_url: String,
}

impl Config {
    pub fn new(acp_url: String) -> Self {
        Self { acp_url }
    }
}

pub fn router(config: Config) -> Router {
    Router::new()
        .route("/acp", get(acp_handler))
        .with_state(config)
}

/// The SPA fallback: anything no route claimed. Client-side routes have no
/// file of their own, so they get the shell; real files get themselves.
pub async fn static_handler(uri: Uri) -> Response {
    let path = uri.path().trim_start_matches('/');
    let path = if path.is_empty() { "index.html" } else { path };
    let relative = Path::new(path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return StatusCode::BAD_REQUEST.into_response();
    }
    match read(path) {
        Some(bytes) => cached(path, bytes),
        None => match read("index.html") {
            Some(bytes) => (
                [(header::CACHE_CONTROL, "no-cache")],
                mime_response("index.html", bytes),
            )
                .into_response(),
            None => StatusCode::NOT_FOUND.into_response(),
        },
    }
}

fn cached(path: &str, bytes: Vec<u8>) -> Response {
    // Vite hashes everything under assets/, so those are immutable forever;
    // the shell must be revalidated or a deploy never reaches a client.
    let control = if path.starts_with("assets/") {
        "public, max-age=31536000, immutable"
    } else {
        "no-cache"
    };
    (
        [(header::CACHE_CONTROL, control)],
        mime_response(path, bytes),
    )
        .into_response()
}

fn mime_response(path: &str, bytes: Vec<u8>) -> Response {
    let mime = mime_guess::from_path(path).first_or_octet_stream();
    ([(header::CONTENT_TYPE, mime.as_ref())], bytes).into_response()
}

#[cfg(not(feature = "dev-web"))]
fn read(path: &str) -> Option<Vec<u8>> {
    embedded::Assets::get(path).map(|file| file.data.to_vec())
}

#[cfg(feature = "dev-web")]
fn read(path: &str) -> Option<Vec<u8>> {
    std::fs::read(Path::new(DIST).join(path)).ok()
}

// ---- /acp -----------------------------------------------------------------

async fn acp_handler(
    State(config): State<Config>,
    headers: HeaderMap,
    upgrade: WebSocketUpgrade,
) -> Response {
    if !crate::ws::origin_allowed(&headers) {
        let origin = headers
            .get(header::ORIGIN)
            .and_then(|value| value.to_str().ok())
            .unwrap_or("?");
        return (
            StatusCode::FORBIDDEN,
            format!("crow-web serves loopback clients only, not {origin}"),
        )
            .into_response();
    }
    upgrade.on_upgrade(move |socket| proxy(socket, config.acp_url))
}

async fn proxy(socket: WebSocket, acp_url: String) {
    let upstream = match tokio_tungstenite::connect_async(&acp_url).await {
        Ok((upstream, _response)) => upstream,
        Err(error) => {
            eprintln!("crow-web: /acp upstream {acp_url} refused: {error}");
            return;
        }
    };
    let (mut client_sink, mut client_stream) = socket.split();
    let (mut upstream_sink, mut upstream_stream) = upstream.split();

    let client_to_upstream = async {
        while let Some(frame) = client_stream.next().await {
            match frame {
                Ok(Message::Text(text)) => {
                    if upstream_sink.send(to_tungstenite_text(text)).await.is_err() {
                        break;
                    }
                }
                Ok(Message::Binary(bytes)) => {
                    if upstream_sink
                        .send(tokio_tungstenite::tungstenite::Message::Binary(bytes))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
                // Ping/pong are each endpoint's own business; both libraries
                // answer them locally.
                Ok(_) => {}
                Err(_) => break,
            }
        }
    };
    let upstream_to_client = async {
        use tokio_tungstenite::tungstenite::Message as Up;
        while let Some(frame) = upstream_stream.next().await {
            match frame {
                Ok(Up::Text(text)) => {
                    if client_sink
                        .send(Message::Text(text.as_str().into()))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
                Ok(Up::Binary(bytes)) => {
                    if client_sink.send(Message::Binary(bytes)).await.is_err() {
                        break;
                    }
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
    };
    // Whichever side hangs up first ends the session; dropping the sinks
    // closes the other socket.
    tokio::select! {
        _ = client_to_upstream => {}
        _ = upstream_to_client => {}
    }
}

fn to_tungstenite_text(
    text: axum::extract::ws::Utf8Bytes,
) -> tokio_tungstenite::tungstenite::Message {
    tokio_tungstenite::tungstenite::Message::Text(text.as_str().into())
}

#[cfg(test)]
mod tests {
    use super::{cached, static_handler};
    use axum::http::Uri;

    #[tokio::test]
    async fn the_shell_answers_for_client_routes() {
        let response = static_handler(Uri::from_static("/threads/42")).await;
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        assert!(String::from_utf8_lossy(&body).contains("<div id=\"root\">"));
    }

    #[tokio::test]
    async fn traversal_is_refused() {
        let response = static_handler(Uri::from_static("/../etc/passwd")).await;
        assert_eq!(response.status(), axum::http::StatusCode::BAD_REQUEST);
    }

    #[test]
    fn hashed_assets_are_immutable_and_the_shell_is_not() {
        let assets = cached("assets/index-abc.js", vec![]);
        assert_eq!(
            assets.headers()[axum::http::header::CACHE_CONTROL],
            "public, max-age=31536000, immutable"
        );
        let shell = cached("index.html", vec![]);
        assert_eq!(
            shell.headers()[axum::http::header::CACHE_CONTROL],
            "no-cache"
        );
    }
}

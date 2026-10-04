//! The `/fs` websocket: JSON requests in, JSON replies and pushed events out.
//!
//! One socket per browser tab. Every socket is a *client id* in the registry,
//! which is what lets two tabs share one buffer without one tab's close
//! yanking it out from under the other. The server pushes what it knows — a
//! `hello` on connect, a `buffer` echo after every write/commit, an `fs` event
//! after anything that moves the tree — so no client has to poll or guess.
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use anyhow::{anyhow, Result};
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use futures::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::sync::{broadcast, mpsc};

use crate::fs::{Buffers, FileView};

/// Everything the server sends, in one flat envelope: a reply carries the
/// request's `id`, an event does not.
#[derive(Debug, Serialize)]
pub struct Out {
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ok: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    event: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<Value>,
}

impl Out {
    fn ok(id: u64, ok: Value) -> Self {
        Self {
            id: Some(id),
            ok: Some(ok),
            error: None,
            event: None,
            data: None,
        }
    }

    fn err(id: u64, error: String) -> Self {
        Self {
            id: Some(id),
            ok: None,
            error: Some(error),
            event: None,
            data: None,
        }
    }

    fn event(event: &'static str, data: Value) -> Self {
        Self {
            id: None,
            ok: None,
            error: None,
            event: Some(event),
            data: Some(data),
        }
    }

    fn to_json(&self) -> String {
        serde_json::to_string(self).expect("Out is serializable")
    }
}

/// The operations a client may ask for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Op {
    /// One level of the tree at `path` (`""` is the root).
    Tree,
    /// Open (or re-attach to) the buffer at `path` and return it whole.
    Read,
    /// Replace the buffer's content; marks it dirty, touches no disk.
    Write,
    /// Save the buffer to disk and clear dirty.
    Commit,
    /// Give up this client's claim on the buffer.
    Close,
    Mkdir,
    Rename,
    Delete,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Request {
    /// Correlation id, echoed back on the reply. Absent means 0.
    #[serde(default)]
    pub id: u64,
    pub op: Op,
    /// Root-relative path; `tree` also accepts `""`.
    #[serde(default)]
    pub path: String,
    /// Rename target.
    #[serde(default)]
    pub to: String,
    /// Write payload.
    #[serde(default)]
    pub text: Option<String>,
}

/// Shared by every connection: the registry, the event fan-out and the client
/// id counter.
#[derive(Clone)]
pub struct Fs {
    root: String,
    buffers: Arc<Mutex<Buffers>>,
    events: broadcast::Sender<String>,
    clients: Arc<AtomicU64>,
}

impl Fs {
    pub fn new(root: PathBuf) -> Result<Self> {
        let display = root.display().to_string();
        let (events, _) = broadcast::channel(256);
        Ok(Self {
            root: display,
            buffers: Arc::new(Mutex::new(Buffers::new(root)?)),
            events,
            clients: Arc::new(AtomicU64::new(1)),
        })
    }

    pub fn root(&self) -> &str {
        &self.root
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Buffers> {
        self.buffers.lock().expect("the fs registry lock")
    }

    fn next_client(&self) -> u64 {
        self.clients.fetch_add(1, Ordering::Relaxed)
    }

    fn publish(&self, out: Out) {
        // No receivers is the normal case (one tab, nobody else listening).
        let _ = self.events.send(out.to_json());
    }

    /// What a fresh socket is told before it asks anything: the root, and
    /// every buffer the server is already holding — which is how a reloaded
    /// page finds the work it left dirty instead of trusting localStorage.
    fn hello(&self) -> Out {
        let buffers = self.lock();
        let views: Vec<FileView> = buffers
            .open_paths()
            .iter()
            .filter_map(|path| buffers.view_of(path).ok().flatten())
            .collect();
        Out::event("hello", json!({ "root": self.root, "buffers": views }))
    }
}

/// Runs on a blocking thread: the ops are short synchronous disk work and the
/// registry lock is never held across an await.
fn run(fs: &Fs, client: u64, req: Request) -> Out {
    let id = req.id;
    match dispatch(fs, client, &req) {
        Ok((reply, events)) => {
            for event in events {
                fs.publish(event);
            }
            Out::ok(id, reply)
        }
        // `{:#}` flattens the anyhow context chain into one readable line.
        Err(e) => Out::err(id, format!("{e:#}")),
    }
}

fn dispatch(fs: &Fs, client: u64, req: &Request) -> Result<(Value, Vec<Out>)> {
    let mut buffers = fs.lock();
    let path = &req.path;
    match req.op {
        Op::Tree => Ok((json!(buffers.list_dir(path)?), vec![])),
        Op::Read => Ok((json!(buffers.open(client, path)?), vec![])),
        Op::Write => {
            let text = req
                .text
                .clone()
                .ok_or_else(|| anyhow!("write needs \"text\""))?;
            let view = buffers.write(client, path, text)?;
            Ok((json!(view), vec![Out::event("buffer", json!(view))]))
        }
        Op::Commit => {
            let view = buffers.commit(path)?;
            Ok((json!(view), vec![Out::event("buffer", json!(view))]))
        }
        // No event: a close changes neither the disk nor what another tab
        // shows. The reply tells the caller whether the buffer survived.
        Op::Close => Ok((json!(buffers.close(client, path)?), vec![])),
        Op::Mkdir => {
            buffers.mkdir(path)?;
            Ok((json!({ "path": path }), vec![moved("mkdir", path, None)]))
        }
        Op::Rename => {
            buffers.rename(path, &req.to)?;
            Ok((
                json!({ "path": path, "to": req.to }),
                vec![moved("rename", path, Some(&req.to))],
            ))
        }
        Op::Delete => {
            buffers.delete(path)?;
            Ok((json!({ "path": path }), vec![moved("delete", path, None)]))
        }
    }
}

/// The tree-invalidation push: `kind` says what happened, `path` says where,
/// and a client refreshes the parent of each.
fn moved(kind: &'static str, path: &str, to: Option<&str>) -> Out {
    Out::event(
        "fs",
        json!({ "kind": kind, "path": path, "to": to, "parent": parent_of(path) }),
    )
}

fn parent_of(path: &str) -> &str {
    match path.rsplit_once('/') {
        Some((parent, _)) => parent,
        None => "",
    }
}

/// A loopback port is reachable from every page in the user's browser, and a
/// websocket gets no CORS preflight — without this, any website the user
/// visits could read and rewrite the served tree. No Origin at all means it is
/// not a browser (curl, the python test client, the rust binary); anything
/// else has to be loopback.
fn origin_allowed(headers: &HeaderMap) -> bool {
    let Some(origin) = headers
        .get(axum::http::header::ORIGIN)
        .and_then(|value| value.to_str().ok())
    else {
        return true;
    };
    let Some(host) = origin
        .split_once("://")
        .map(|(_, rest)| rest.split('/').next().unwrap_or(rest))
        .map(|authority| match authority.rsplit_once(':') {
            Some((host, _)) => host,
            None => authority,
        })
    else {
        return false;
    };
    matches!(host, "localhost" | "127.0.0.1" | "[::1]")
}

pub async fn handler(
    State(fs): State<Fs>,
    headers: HeaderMap,
    upgrade: WebSocketUpgrade,
) -> Response {
    if !origin_allowed(&headers) {
        let origin = headers
            .get(axum::http::header::ORIGIN)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("?");
        return (
            axum::http::StatusCode::FORBIDDEN,
            format!("crow-web serves loopback clients only, not {origin}"),
        )
            .into_response();
    }
    upgrade.on_upgrade(move |socket| serve(socket, fs))
}

async fn serve(socket: WebSocket, fs: Fs) {
    let client = fs.next_client();
    let (sink, mut stream) = socket.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<Message>();
    let mut events = fs.events.subscribe();

    let writer = tokio::spawn(async move {
        let mut sink = sink;
        while let Some(message) = rx.recv().await {
            if sink.send(message).await.is_err() {
                break;
            }
        }
    });

    let _ = tx.send(Message::Text(fs.hello().to_json().into()));

    // Fan the broadcast out to this socket. A lagged receiver missed events,
    // not correctness: the next `tree`/`read` is a full snapshot.
    let pump = {
        let tx = tx.clone();
        async move {
            loop {
                match events.recv().await {
                    Ok(json) => {
                        if tx.send(Message::Text(json.into())).is_err() {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(skipped)) => {
                        eprintln!("crow-web: a /fs client lagged, dropped {skipped} events");
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        }
    };

    let reader = {
        let tx = tx.clone();
        let fs = fs.clone();
        async move {
            while let Some(frame) = stream.next().await {
                let frame = match frame {
                    Ok(frame) => frame,
                    Err(_) => break,
                };
                let Message::Text(text) = frame else {
                    // Ping/pong are tungstenite's business; binary is not ours.
                    continue;
                };
                let out = match serde_json::from_str::<Request>(&text) {
                    Ok(req) => {
                        let fs = fs.clone();
                        match tokio::task::spawn_blocking(move || run(&fs, client, req)).await {
                            Ok(out) => out,
                            Err(e) => Out::err(0, format!("the op panicked: {e}")),
                        }
                    }
                    Err(e) => Out::err(0, format!("bad request: {e}")),
                };
                if tx.send(Message::Text(out.to_json().into())).is_err() {
                    break;
                }
            }
        }
    };

    tokio::select! {
        _ = pump => {}
        _ = reader => {}
    }

    // The socket is gone. Give up its claims; anything that drops is work
    // nobody had saved, but the other tabs still want to hear about it.
    for path in fs.lock().disconnect(client) {
        fs.publish(moved("close", &path, None));
    }
    drop(tx);
    let _ = writer.await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::header::ORIGIN;
    use axum::http::HeaderValue;

    // Same hand-rolled temp root as fs.rs: no tempfile dev-dependency here.
    struct TempRoot {
        path: PathBuf,
    }

    impl TempRoot {
        fn new(name: &str) -> Self {
            use std::sync::atomic::{AtomicU64, Ordering};
            static N: AtomicU64 = AtomicU64::new(0);
            let dir = std::env::temp_dir().join(format!(
                "crow-web-ws-{name}-{}-{}",
                std::process::id(),
                N.fetch_add(1, Ordering::Relaxed),
            ));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("create temp root");
            Self { path: dir }
        }

        fn put(&self, rel: &str, content: &str) {
            let abs = self.path.join(rel);
            std::fs::create_dir_all(abs.parent().unwrap()).expect("parent");
            std::fs::write(&abs, content).expect("write fixture");
        }

        fn disk(&self, rel: &str) -> Option<String> {
            std::fs::read_to_string(self.path.join(rel)).ok()
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }

    fn server(name: &str) -> (TempRoot, Fs) {
        let root = TempRoot::new(name);
        let fs = Fs::new(root.path.clone()).expect("server state");
        (root, fs)
    }

    fn req(json: &str) -> Request {
        serde_json::from_str(json).expect("request parses")
    }

    /// One round trip: request JSON in, envelope JSON out.
    fn call(fs: &Fs, client: u64, json: &str) -> Value {
        let out = run(fs, client, req(json));
        serde_json::from_str(&out.to_json()).expect("envelope is json")
    }

    fn origin(value: Option<&str>) -> HeaderMap {
        let mut headers = HeaderMap::new();
        if let Some(value) = value {
            headers.insert(ORIGIN, HeaderValue::from_str(value).unwrap());
        }
        headers
    }

    #[test]
    fn origin_policy_allows_loopback_and_non_browsers() {
        for allowed in [
            None, // curl, the python client, the rust binary
            Some("http://localhost:5173"),
            Some("http://127.0.0.1:5173"),
            Some("http://[::1]:5173"),
            Some("https://127.0.0.1"),
        ] {
            assert!(
                origin_allowed(&origin(allowed)),
                "{allowed:?} should be allowed"
            );
        }
        for denied in [
            Some("https://evil.com"),
            Some("http://localhost.evil.com"),
            Some("http://127.0.0.1.evil.com"),
            Some("null"),
            Some("garbage"),
        ] {
            assert!(
                !origin_allowed(&origin(denied)),
                "{denied:?} should be refused"
            );
        }
    }

    #[test]
    fn envelope_carries_id_ok_or_error_and_never_both() {
        let (root, fs) = server("envelope");
        root.put("a.txt", "hello");
        let ok = call(&fs, 1, r#"{"id":7,"op":"read","path":"a.txt"}"#);
        assert_eq!(ok["id"], 7);
        assert_eq!(ok["ok"]["path"], "a.txt");
        assert_eq!(ok["ok"]["content"], "hello");
        assert_eq!(ok["ok"]["dirty"], false);
        assert!(ok["ok"]["mtime"].is_number());
        assert!(ok.get("error").is_none(), "no error key at all");
        assert!(ok.get("event").is_none(), "a reply is not an event");

        let err = call(&fs, 1, r#"{"id":9,"op":"read","path":"ghost.txt"}"#);
        assert_eq!(err["id"], 9);
        assert!(err["error"].as_str().unwrap().contains("no such file"));
        assert!(err.get("ok").is_none());
    }

    #[test]
    fn a_request_without_an_op_does_not_parse() {
        assert!(serde_json::from_str::<Request>(r#"{"id":1}"#).is_err());
        assert!(serde_json::from_str::<Request>(r#"{"id":1,"op":"nope"}"#).is_err());
    }

    #[test]
    fn write_then_commit_over_the_protocol() {
        let (root, fs) = server("save");
        root.put("a.txt", "hello");
        call(&fs, 1, r#"{"id":1,"op":"read","path":"a.txt"}"#);
        let wrote = call(
            &fs,
            1,
            r#"{"id":2,"op":"write","path":"a.txt","text":"hi there"}"#,
        );
        assert_eq!(wrote["ok"]["dirty"], true);
        assert_eq!(root.disk("a.txt").unwrap(), "hello", "write does not save");

        let committed = call(&fs, 1, r#"{"id":3,"op":"commit","path":"a.txt"}"#);
        assert_eq!(committed["ok"]["dirty"], false);
        assert_eq!(root.disk("a.txt").unwrap(), "hi there");

        let missing = call(&fs, 1, r#"{"id":4,"op":"write","path":"a.txt"}"#);
        assert!(
            missing["error"].as_str().unwrap().contains("text"),
            "{missing}"
        );
    }

    #[test]
    fn tree_is_lazy_and_carries_dirty_flags() {
        let (root, fs) = server("tree");
        root.put("src/main.rs", "fn main() {}");
        root.put("README.md", "# hi");
        call(
            &fs,
            1,
            r#"{"id":1,"op":"write","path":"README.md","text":"edited"}"#,
        );

        let tree = call(&fs, 1, r#"{"id":2,"op":"tree","path":""}"#);
        assert_eq!(tree["ok"]["path"], "");
        let entries = tree["ok"]["entries"].as_array().unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0]["type"], "dir", "directories first");
        assert_eq!(entries[0]["name"], "src");
        assert_eq!(entries[1]["name"], "README.md");
        assert_eq!(entries[1]["dirty"], true);

        let nested = call(&fs, 1, r#"{"id":3,"op":"tree","path":"src"}"#);
        assert_eq!(nested["ok"]["entries"][0]["path"], "src/main.rs");
        let escaped = call(&fs, 1, r#"{"id":4,"op":"tree","path":".."}"#);
        assert!(
            escaped["error"].as_str().unwrap().contains("escapes"),
            "{escaped}"
        );
    }

    #[test]
    fn mkdir_rename_delete_move_the_disk() {
        let (root, fs) = server("mutate");
        root.put("old.txt", "bytes");
        assert_eq!(
            call(&fs, 1, r#"{"id":1,"op":"mkdir","path":"pkg"}"#)["ok"]["path"],
            "pkg"
        );
        assert!(root.path.join("pkg").is_dir());

        call(
            &fs,
            1,
            r#"{"id":2,"op":"rename","path":"old.txt","to":"pkg/new.txt"}"#,
        );
        assert_eq!(root.disk("pkg/new.txt").unwrap(), "bytes");
        assert!(root.disk("old.txt").is_none());

        call(&fs, 1, r#"{"id":3,"op":"delete","path":"pkg"}"#);
        assert!(!root.path.join("pkg").exists());
        let err = call(&fs, 1, r#"{"id":4,"op":"delete","path":"pkg"}"#);
        assert!(err["error"].is_string(), "deleting twice is an error");
    }

    #[test]
    fn two_clients_share_one_buffer_and_close_is_refcounted() {
        let (root, fs) = server("shared");
        root.put("a.txt", "hello");
        call(&fs, 1, r#"{"id":1,"op":"read","path":"a.txt"}"#);
        call(&fs, 2, r#"{"id":2,"op":"read","path":"a.txt"}"#);
        let wrote = call(
            &fs,
            1,
            r#"{"id":3,"op":"write","path":"a.txt","text":"from tab one"}"#,
        );
        assert_eq!(wrote["ok"]["dirty"], true);

        let seen = call(&fs, 2, r#"{"id":4,"op":"read","path":"a.txt"}"#);
        assert_eq!(
            seen["ok"]["content"], "from tab one",
            "one buffer, two tabs"
        );

        let close = call(&fs, 1, r#"{"id":5,"op":"close","path":"a.txt"}"#);
        assert_eq!(close["ok"]["state"], "kept");
        assert_eq!(close["ok"]["dirty"], true);
        let close = call(&fs, 2, r#"{"id":6,"op":"close","path":"a.txt"}"#);
        assert_eq!(
            close["ok"]["state"], "kept",
            "dirty work outlives both tabs"
        );

        // A socket that vanishes without closing gives up its claims.
        call(&fs, 3, r#"{"id":7,"op":"read","path":"a.txt"}"#);
        assert_eq!(
            fs.lock().disconnect(3),
            Vec::<String>::new(),
            "dirty is kept"
        );
        // Client 4 saves a path it never opened: the commit succeeds, and with
        // the buffer clean and unheld there is nothing left to keep.
        let committed = call(&fs, 4, r#"{"id":8,"op":"commit","path":"a.txt"}"#);
        assert_eq!(committed["ok"]["dirty"], false);
        assert_eq!(root.disk("a.txt").unwrap(), "from tab one");
        assert!(
            fs.lock().open_paths().is_empty(),
            "a clean buffer nobody holds is dropped"
        );
    }

    #[test]
    fn mutations_are_broadcast_and_reads_are_not() {
        let (_root, fs) = server("events");
        let mut events = fs.events.subscribe();
        fs.publish(fs.hello());
        call(
            &fs,
            1,
            r#"{"id":1,"op":"write","path":"new.txt","text":"x"}"#,
        );
        call(&fs, 1, r#"{"id":2,"op":"read","path":"new.txt"}"#);
        call(&fs, 1, r#"{"id":3,"op":"mkdir","path":"d"}"#);
        call(&fs, 1, r#"{"id":4,"op":"commit","path":"new.txt"}"#);

        let hello: Value = serde_json::from_str(&events.try_recv().unwrap()).unwrap();
        assert_eq!(hello["event"], "hello");
        assert_eq!(hello["data"]["buffers"].as_array().unwrap().len(), 0);
        assert_eq!(hello["data"]["root"], fs.root());

        let wrote: Value = serde_json::from_str(&events.try_recv().unwrap()).unwrap();
        assert_eq!(wrote["event"], "buffer");
        assert_eq!(wrote["data"]["path"], "new.txt");
        assert_eq!(wrote["data"]["dirty"], true);
        assert!(wrote.get("id").is_none(), "an event has no correlation id");

        let mkdir: Value = serde_json::from_str(&events.try_recv().unwrap()).unwrap();
        assert_eq!(mkdir["event"], "fs");
        assert_eq!(mkdir["data"]["kind"], "mkdir");
        assert_eq!(mkdir["data"]["path"], "d");
        assert_eq!(mkdir["data"]["parent"], "");

        let committed: Value = serde_json::from_str(&events.try_recv().unwrap()).unwrap();
        assert_eq!(committed["data"]["dirty"], false);
        assert!(committed["data"]["mtime"].is_number());
        assert!(events.try_recv().is_err(), "the read published nothing");
    }

    #[test]
    fn rename_tells_clients_which_parent_to_refresh() {
        let (root, fs) = server("rename-event");
        root.put("pkg/a.txt", "a");
        let mut events = fs.events.subscribe();
        call(
            &fs,
            1,
            r#"{"id":1,"op":"rename","path":"pkg/a.txt","to":"pkg/b.txt"}"#,
        );
        let event: Value = serde_json::from_str(&events.try_recv().unwrap()).unwrap();
        assert_eq!(event["data"]["kind"], "rename");
        assert_eq!(event["data"]["to"], "pkg/b.txt");
        assert_eq!(event["data"]["parent"], "pkg");
        assert_eq!(root.disk("pkg/b.txt").unwrap(), "a");
    }

    #[test]
    fn parent_of_handles_the_root() {
        assert_eq!(parent_of("a.txt"), "");
        assert_eq!(parent_of("src/a.txt"), "src");
        assert_eq!(parent_of("a/b/c.txt"), "a/b");
    }
}

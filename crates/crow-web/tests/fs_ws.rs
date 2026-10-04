//! End to end over a real socket: the shipped `crow-web` binary, a tempdir as
//! its root, and a websocket client per browser tab.
//!
//! The unit tests in `src/fs.rs` and `src/ws.rs` cover the registry and the
//! protocol handler in isolation. This is the tier above them — the same shape
//! the browser uses — so it asserts what the *disk* looks like after each op,
//! because the server owning the state is only true if the bytes moved.
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use futures::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio_tungstenite::tungstenite::{Error as WsError, Message};

type WsStream =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

/// A running server against a throwaway root.
struct Server {
    child: Child,
    url: String,
    root: PathBuf,
}

impl Server {
    fn start(name: &str) -> Self {
        let root = temp_root(name);
        std::fs::create_dir_all(root.join("src")).expect("fixture dir");
        std::fs::write(root.join("src/main.rs"), "fn main() {}\n").expect("fixture");
        std::fs::write(root.join("README.md"), "# hello\n").expect("fixture");

        let port = free_port();
        let child = Command::new(env!("CARGO_BIN_EXE_crow-web"))
            .args(["--port", &port.to_string(), "--root"])
            .arg(&root)
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("spawn crow-web");
        // Wait for the listener instead of sleeping a guess.
        let deadline = std::time::Instant::now() + Duration::from_secs(15);
        loop {
            if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
                break;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "crow-web never listened on {port}"
            );
            std::thread::sleep(Duration::from_millis(50));
        }
        Self {
            child,
            url: format!("ws://127.0.0.1:{port}/fs"),
            root,
        }
    }

    fn disk(&self, rel: &str) -> Option<String> {
        std::fs::read_to_string(self.root.join(rel)).ok()
    }

    fn exists(&self, rel: &str) -> bool {
        self.root.join(rel).exists()
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = std::fs::remove_dir_all(&self.root);
    }
}

/// One connected tab: request/reply in order, with pushed events collected.
struct Client {
    ws: WsStream,
    next: u64,
    events: Vec<Value>,
}

impl Client {
    async fn connect(url: &str) -> Self {
        let (ws, _) = tokio_tungstenite::connect_async(url)
            .await
            .expect("connect to /fs");
        let mut client = Self {
            ws,
            next: 0,
            events: Vec::new(),
        };
        // The hello arrives unprompted; keep it where the assertions can see it.
        let hello = client.recv().await.expect("hello");
        client.events.push(hello);
        client
    }

    async fn recv(&mut self) -> Option<Value> {
        loop {
            match self.ws.next().await? {
                Ok(Message::Text(text)) => return Some(serde_json::from_str(&text).expect("json")),
                Ok(_) => continue,
                Err(e) => panic!("websocket error: {e}"),
            }
        }
    }

    /// Sends a request and reads until its reply, stashing any event that
    /// arrives first.
    async fn call(&mut self, request: Value) -> Value {
        self.next += 1;
        let id = self.next;
        let mut request = request;
        request["id"] = json!(id);
        self.ws
            .send(Message::Text(request.to_string().into()))
            .await
            .expect("send");
        loop {
            let message = self.recv().await.expect("server closed mid-request");
            if message.get("id") == Some(&json!(id)) {
                return message;
            }
            self.events.push(message);
        }
    }

    /// Collects whatever the server pushed, waiting briefly for it to arrive.
    async fn drain(&mut self) -> Vec<Value> {
        while let Ok(Some(message)) =
            tokio::time::timeout(Duration::from_millis(300), self.recv()).await
        {
            self.events.push(message);
        }
        std::mem::take(&mut self.events)
    }

    fn hello(&self) -> &Value {
        &self.events[0]
    }
}

/// A handshake request with an Origin, as a browser would send it. Building it
/// from the url keeps tungstenite's own `Sec-WebSocket-*` headers intact.
fn with_origin(url: &str, origin: &str) -> axum::http::Request<()> {
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    let mut request = url.into_client_request().expect("handshake request");
    request.headers_mut().insert(
        axum::http::header::ORIGIN,
        axum::http::HeaderValue::from_str(origin).expect("header value"),
    );
    request
}

fn free_port() -> u16 {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
    listener.local_addr().expect("addr").port()
}

/// Hand-rolled, like the unit tests: no tempfile dev-dependency in this repo.
fn temp_root(name: &str) -> PathBuf {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir().join(format!(
        "crow-web-ws-{name}-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed),
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("create temp root");
    dir
}

#[tokio::test]
async fn every_op_over_a_real_socket() {
    let server = Server::start("all-ops");
    let mut a = Client::connect(&server.url).await;

    // --- hello -------------------------------------------------------------
    assert_eq!(a.hello()["event"], "hello");
    assert_eq!(
        a.hello()["data"]["root"],
        server.root.canonicalize().unwrap().display().to_string()
    );
    assert_eq!(a.hello()["data"]["buffers"], json!([]));

    // --- tree --------------------------------------------------------------
    let tree = a.call(json!({"op": "tree", "path": ""})).await;
    let names: Vec<&str> = tree["ok"]["entries"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, vec!["src", "README.md"], "directories first");
    assert_eq!(tree["ok"]["entries"][1]["path"], "README.md");
    assert_eq!(tree["ok"]["entries"][1]["size"], json!(8));
    let nested = a.call(json!({"op": "tree", "path": "src"})).await;
    assert_eq!(
        nested["ok"]["entries"].as_array().unwrap().len(),
        1,
        "one level"
    );
    let escaped = a.call(json!({"op": "tree", "path": ".."})).await;
    assert!(
        escaped["error"].as_str().unwrap().contains("escapes"),
        "{escaped}"
    );

    // --- read / write / commit --------------------------------------------
    let read = a.call(json!({"op": "read", "path": "src/main.rs"})).await;
    assert_eq!(read["ok"]["content"], "fn main() {}\n");
    assert_eq!(read["ok"]["dirty"], json!(false));
    assert!(read["ok"]["mtime"].is_number());

    let wrote = a
        .call(json!({"op": "write", "path": "src/main.rs", "text": "fn main() { println!(\"hi\"); }\n"}))
        .await;
    assert_eq!(wrote["ok"]["dirty"], json!(true));
    assert_eq!(
        server.disk("src/main.rs").unwrap(),
        "fn main() {}\n",
        "a write must not touch the disk"
    );

    let no_text = a.call(json!({"op": "write", "path": "src/main.rs"})).await;
    assert!(
        no_text["error"].as_str().unwrap().contains("text"),
        "{no_text}"
    );

    let committed = a.call(json!({"op": "commit", "path": "src/main.rs"})).await;
    assert_eq!(committed["ok"]["dirty"], json!(false));
    assert_eq!(
        server.disk("src/main.rs").unwrap(),
        "fn main() { println!(\"hi\"); }\n"
    );
    assert!(
        committed["ok"]["mtime"].as_u64().unwrap() >= read["ok"]["mtime"].as_u64().unwrap(),
        "mtime should not go backwards"
    );

    let missing = a.call(json!({"op": "read", "path": "ghost.rs"})).await;
    assert!(
        missing["error"].as_str().unwrap().contains("no such file"),
        "{missing}"
    );

    // --- mkdir / rename / delete ------------------------------------------
    a.call(json!({"op": "mkdir", "path": "pkg/inner"})).await;
    assert!(server.root.join("pkg/inner").is_dir());
    let twice = a.call(json!({"op": "mkdir", "path": "pkg"})).await;
    assert!(
        twice["error"].as_str().unwrap().contains("already exists"),
        "{twice}"
    );

    a.call(json!({"op": "rename", "path": "src/main.rs", "to": "src/lib.rs"}))
        .await;
    assert!(server.disk("src/lib.rs").is_some() && server.disk("src/main.rs").is_none());
    let clobber = a
        .call(json!({"op": "rename", "path": "src/lib.rs", "to": "README.md"}))
        .await;
    assert!(
        clobber["error"]
            .as_str()
            .unwrap()
            .contains("already exists"),
        "{clobber}"
    );
    a.call(json!({"op": "rename", "path": "src/lib.rs", "to": "src/main.rs"}))
        .await;

    // A new file that was never committed is only a buffer: renaming it moves
    // the registry entry and leaves the disk alone.
    a.call(json!({"op": "write", "path": "pkg/inner/new.rs", "text": "born dirty"}))
        .await;
    assert!(server.disk("pkg/inner/new.rs").is_none());
    a.call(json!({"op": "rename", "path": "pkg/inner/new.rs", "to": "pkg/moved.rs"}))
        .await;
    assert!(
        server.disk("pkg/moved.rs").is_none(),
        "no bytes to move yet"
    );
    let carried = a.call(json!({"op": "read", "path": "pkg/moved.rs"})).await;
    assert_eq!(carried["ok"]["content"], "born dirty");
    assert_eq!(carried["ok"]["dirty"], json!(true));
    a.call(json!({"op": "commit", "path": "pkg/moved.rs"}))
        .await;
    assert_eq!(server.disk("pkg/moved.rs").unwrap(), "born dirty");

    a.call(json!({"op": "delete", "path": "pkg"})).await;
    assert!(!server.exists("pkg"), "delete removes the whole subtree");
    let gone = a
        .call(json!({"op": "commit", "path": "pkg/moved.rs"}))
        .await;
    assert!(
        gone["error"].as_str().unwrap().contains("no open buffer"),
        "delete drops the buffers under it: {gone}"
    );

    // --- two tabs, one buffer ---------------------------------------------
    let mut b = Client::connect(&server.url).await;
    let held: Vec<&str> = b.hello()["data"]["buffers"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["path"].as_str().unwrap())
        .collect();
    assert_eq!(
        held,
        vec!["src/main.rs"],
        "hello reports what the server holds"
    );

    b.call(json!({"op": "read", "path": "README.md"})).await;
    a.call(json!({"op": "write", "path": "README.md", "text": "# edited by tab A"}))
        .await;
    let seen = b.call(json!({"op": "read", "path": "README.md"})).await;
    assert_eq!(
        seen["ok"]["content"], "# edited by tab A",
        "one buffer, two tabs"
    );

    let pushed = b.drain().await;
    assert!(
        pushed
            .iter()
            .any(|e| e["event"] == "buffer" && e["data"]["dirty"] == json!(true)),
        "tab B is told about tab A's edit: {pushed:?}"
    );
    assert!(
        a.drain().await.iter().any(|e| e["event"] == "buffer"),
        "the writer hears its own echo"
    );
    assert_eq!(server.disk("README.md").unwrap(), "# hello\n");

    let close_a = a.call(json!({"op": "close", "path": "README.md"})).await;
    assert_eq!(
        close_a["ok"],
        json!({"state": "kept", "dirty": true}),
        "tab B still holds it"
    );
    let close_b = b.call(json!({"op": "close", "path": "README.md"})).await;
    assert_eq!(
        close_b["ok"],
        json!({"state": "kept", "dirty": true}),
        "dirty work outlives both tabs"
    );

    // --- a socket that vanishes -------------------------------------------
    std::fs::write(server.root.join("only-c.txt"), "clean work\n").expect("fixture");
    {
        let mut c = Client::connect(&server.url).await;
        c.call(json!({"op": "read", "path": "README.md"})).await;
        c.call(json!({"op": "read", "path": "only-c.txt"})).await;
        // Dropped here without a close frame: the browser tab was killed.
    }
    tokio::time::sleep(Duration::from_millis(300)).await;

    let mut d = Client::connect(&server.url).await;
    let held: Vec<&str> = d.hello()["data"]["buffers"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["path"].as_str().unwrap())
        .collect();
    assert!(
        held.contains(&"README.md"),
        "dirty survives the socket: {held:?}"
    );
    assert!(
        !held.contains(&"only-c.txt"),
        "clean and unheld is dropped: {held:?}"
    );
    assert!(
        held.contains(&"src/main.rs"),
        "tab A still holds its file: {held:?}"
    );
    let reread = d.call(json!({"op": "read", "path": "only-c.txt"})).await;
    assert_eq!(
        reread["ok"]["content"], "clean work\n",
        "the disk is the authority again"
    );
    let dirty = d.call(json!({"op": "read", "path": "README.md"})).await;
    assert_eq!(dirty["ok"]["content"], "# edited by tab A");
}

#[tokio::test]
async fn a_foreign_origin_is_refused_and_loopback_is_not() {
    let server = Server::start("origin");

    let err = tokio_tungstenite::connect_async(with_origin(&server.url, "https://evil.example"))
        .await
        .expect_err("a website must not reach the served tree");
    match err {
        WsError::Http(response) => assert_eq!(response.status(), 403, "{response:?}"),
        other => panic!("expected an HTTP refusal, got {other:?}"),
    }

    let (mut ws, response) =
        tokio_tungstenite::connect_async(with_origin(&server.url, "http://localhost:5173"))
            .await
            .expect("the vite dev origin is allowed");
    assert_eq!(response.status(), 101);
    let hello = ws.next().await.expect("hello").expect("text frame");
    let Message::Text(text) = hello else {
        panic!("expected a text frame");
    };
    assert_eq!(
        serde_json::from_str::<Value>(&text).unwrap()["event"],
        "hello"
    );
}

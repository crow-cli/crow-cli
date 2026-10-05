//! The `/pty` websocket: one shell per connection, bytes both ways.
//!
//! xterm.js is the terminal emulator — there is no VT parsing on this side,
//! only spawn, resize, kill and the pump. The wire splits on frame type:
//! BINARY frames are pty bytes in both directions (a terminal stream is bytes,
//! and a UTF-8 sequence can be split across two reads, so text frames would
//! corrupt it); TEXT frames are JSON control:
//!
//! ```text
//! client → server   {"type":"resize","cols":120,"rows":32}
//! server → client   {"type":"hello","pid":4242,"cols":120,"rows":32}
//! server → client   {"type":"exit","code":0,"signal":null}
//! server → client   {"type":"error","error":"..."}   (only if spawn failed)
//! ```
//!
//! The initial size rides in on the query string (`/pty?cols=120&rows=32`) so
//! the shell is born at the right size instead of reflowing a frame later.
//! A socket closing kills its shell: a terminal nobody is watching is a
//! process leak, not a session.
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result};
use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Query, State};
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use futures::{SinkExt, StreamExt};
use portable_pty::{native_pty_system, Child, CommandBuilder, ExitStatus, MasterPty, PtySize};
use serde::Deserialize;
use serde_json::json;
use tokio::sync::mpsc;

use crate::ws::origin_allowed;

pub const DEFAULT_COLS: u16 = 80;
pub const DEFAULT_ROWS: u16 = 24;

/// What shells are spawned into. One per server, shared by every connection.
///
/// The cwd is read from the `/fs` state at spawn time, not baked in: when a
/// re-root moves the served tree, the *next* terminal tab starts there. A
/// shell that is already running stays where it was born — the same rule as a
/// real terminal's "cd" being per-shell, never global.
#[derive(Clone)]
pub struct Config {
    shell: String,
    fs: crate::ws::Fs,
}

impl Config {
    /// `shell` falls back to `$SHELL`, then to bash: under a systemd unit
    /// there is no `$SHELL`, and failing at spawn time per connection would be
    /// a worse answer than starting the shell the machine has.
    pub fn new(fs: crate::ws::Fs, shell: Option<String>) -> Self {
        let shell = shell
            .unwrap_or_else(|| std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string()));
        Self { shell, fs }
    }

    pub fn shell(&self) -> &str {
        &self.shell
    }

    fn cwd(&self) -> PathBuf {
        PathBuf::from(self.fs.root())
    }
}

pub fn router(config: Config) -> Router {
    Router::new().route("/pty", get(handler)).with_state(config)
}

/// The size the client's terminal already has, so the first prompt is drawn
/// at the right width.
#[derive(Debug, Deserialize)]
pub struct SizeQuery {
    pub cols: Option<u16>,
    pub rows: Option<u16>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Control {
    Resize { cols: u16, rows: u16 },
}

async fn handler(
    State(config): State<Config>,
    headers: HeaderMap,
    Query(query): Query<SizeQuery>,
    upgrade: WebSocketUpgrade,
) -> Response {
    // Same rule as /fs: a loopback port is reachable from any page in the
    // user's browser, and a websocket gets no CORS preflight.
    if !origin_allowed(&headers) {
        let origin = headers
            .get(axum::http::header::ORIGIN)
            .and_then(|value| value.to_str().ok())
            .unwrap_or("?");
        return (
            axum::http::StatusCode::FORBIDDEN,
            format!("crow-web serves loopback clients only, not {origin}"),
        )
            .into_response();
    }
    let cols = query.cols.filter(|c| *c > 0).unwrap_or(DEFAULT_COLS);
    let rows = query.rows.filter(|r| *r > 0).unwrap_or(DEFAULT_ROWS);
    upgrade.on_upgrade(move |socket| serve(socket, config, cols, rows))
}

/// A live shell plus the two threads that move its bytes.
struct Session {
    /// The master fd is what keeps the pty alive, so it outlives the child and
    /// is dropped last. Shared with the inbound pump for resizes; the Mutex is
    /// what makes the `Arc` Sync (the trait object is only Send), and a resize
    /// is one ioctl — never held across an await.
    master: Arc<Mutex<Box<dyn MasterPty + Send>>>,
    child: Option<Box<dyn Child + Send + Sync>>,
    /// Bytes for the shell's stdin. Dropping every sender ends the writer
    /// thread; the reader thread ends at the pty's EOF.
    input: std::sync::mpsc::Sender<Vec<u8>>,
    pid: Option<u32>,
}

impl Session {
    fn spawn(
        config: &Config,
        cols: u16,
        rows: u16,
    ) -> Result<(Self, mpsc::UnboundedReceiver<Vec<u8>>)> {
        let pair = native_pty_system()
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .context("openpty")?;
        let mut command = CommandBuilder::new(&config.shell);
        command.cwd(config.cwd());
        command.env("TERM", "xterm-256color");
        command.env("COLORTERM", "truecolor");
        let child = pair
            .slave
            .spawn_command(command)
            .with_context(|| format!("spawn {} in {}", config.shell, config.cwd().display()))?;
        let pid = child.process_id();

        let (out_tx, out_rx) = mpsc::unbounded_channel::<Vec<u8>>();
        let mut reader = pair
            .master
            .try_clone_reader()
            .context("clone the pty reader")?;
        std::thread::Builder::new()
            .name(format!("crow-web-pty-out-{pid:?}"))
            .spawn(move || {
                let mut buf = [0u8; 8192];
                loop {
                    match reader.read(&mut buf) {
                        Ok(0) => break, // EOF: the shell is gone
                        Ok(n) => {
                            if out_tx.send(buf[..n].to_vec()).is_err() {
                                break;
                            }
                        }
                        Err(_) => break,
                    }
                }
            })
            .context("spawn the pty reader thread")?;

        let (in_tx, in_rx) = std::sync::mpsc::channel::<Vec<u8>>();
        let mut writer = pair.master.take_writer().context("take the pty writer")?;
        std::thread::Builder::new()
            .name(format!("crow-web-pty-in-{pid:?}"))
            .spawn(move || {
                while let Ok(data) = in_rx.recv() {
                    // A write can block when the child is not reading; that is
                    // exactly why this is a thread and not the async task.
                    if writer.write_all(&data).is_err() {
                        break;
                    }
                }
            })
            .context("spawn the pty writer thread")?;

        // The parent must not hold the slave open, or the pty never sees EOF
        // when the shell exits and the reader thread blocks forever.
        drop(pair.slave);
        Ok((
            Self {
                master: Arc::new(Mutex::new(pair.master)),
                child: Some(child),
                input: in_tx,
                pid,
            },
            out_rx,
        ))
    }

    /// Ends the shell if it is still running and reports how it went.
    async fn reap(&mut self) -> Option<ExitStatus> {
        let mut child = self.child.take()?;
        tokio::task::spawn_blocking(move || {
            if matches!(child.try_wait(), Ok(None)) {
                let _ = child.kill();
            }
            child.wait().ok()
        })
        .await
        .ok()
        .flatten()
    }
}

/// Tells the kernel the terminal changed size, which is what makes the shell
/// (and vim, and anything else reading the winsize) redraw. One ioctl.
fn resize(master: &Mutex<Box<dyn MasterPty + Send>>, cols: u16, rows: u16) -> Result<()> {
    master
        .lock()
        .expect("the pty master lock")
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .context("resize the pty")
}

impl Drop for Session {
    fn drop(&mut self) {
        // Never leave a shell behind, even if the handler panicked on the way
        // past a spawn.
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
        }
    }
}

async fn serve(socket: WebSocket, config: Config, cols: u16, rows: u16) {
    let (mut session, mut output) = match Session::spawn(&config, cols, rows) {
        Ok(spawned) => spawned,
        Err(e) => {
            let (mut sink, _) = socket.split();
            let _ = sink
                .send(Message::Text(
                    json!({"type": "error", "error": format!("{e:#}")})
                        .to_string()
                        .into(),
                ))
                .await;
            let _ = sink.close().await;
            return;
        }
    };

    let (sink, mut stream) = socket.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<Message>();
    let writer = tokio::spawn(async move {
        let mut sink = sink;
        while let Some(message) = rx.recv().await {
            if sink.send(message).await.is_err() {
                break;
            }
        }
    });

    let _ = tx.send(Message::Text(
        json!({ "type": "hello", "pid": session.pid, "cols": cols, "rows": rows })
            .to_string()
            .into(),
    ));

    // Browser → shell: binary frames are stdin, text frames are control.
    let inbound = {
        let input = session.input.clone();
        let master = session.master.clone();
        async move {
            while let Some(frame) = stream.next().await {
                match frame {
                    Ok(Message::Binary(bytes)) => {
                        if input.send(bytes.to_vec()).is_err() {
                            break;
                        }
                    }
                    Ok(Message::Text(text)) => match serde_json::from_str::<Control>(&text) {
                        Ok(Control::Resize { cols, rows }) => {
                            if let Err(e) = resize(&master, cols, rows) {
                                eprintln!("crow-web: pty resize failed: {e:#}");
                            }
                        }
                        Err(e) => eprintln!("crow-web: bad /pty control frame: {e}"),
                    },
                    Ok(Message::Close(_)) | Err(_) => break,
                    Ok(_) => {}
                }
            }
        }
    };

    // Shell → browser. The channel closing is the shell's EOF.
    let outbound = {
        let tx = tx.clone();
        async move {
            while let Some(bytes) = output.recv().await {
                if tx.send(Message::Binary(bytes.into())).is_err() {
                    break;
                }
            }
        }
    };

    tokio::select! {
        _ = inbound => {}
        _ = outbound => {}
    }

    let exit = session.reap().await;
    let _ = tx.send(Message::Text(
        json!({
            "type": "exit",
            "code": exit.as_ref().map(|status| status.exit_code()),
            "signal": exit.as_ref().and_then(|status| status.signal().map(str::to_string)),
        })
        .to_string()
        .into(),
    ));
    drop(tx);
    let _ = writer.await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    /// `/bin/sh`, not `$SHELL`: no rc files, no prompt themes, no surprises.
    fn config(name: &str) -> (PathBuf, Config) {
        let root = temp_root(name);
        let fs = crate::ws::Fs::new(root.clone()).expect("fs state");
        let config = Config::new(fs, Some("/bin/sh".to_string()));
        (root, config)
    }

    fn temp_root(name: &str) -> PathBuf {
        use std::sync::atomic::{AtomicU64, Ordering};
        static N: AtomicU64 = AtomicU64::new(0);
        let dir = std::env::temp_dir().join(format!(
            "crow-web-pty-{name}-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::Relaxed),
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("create temp root");
        dir
    }

    fn alive(pid: u32) -> bool {
        std::path::Path::new(&format!("/proc/{pid}")).exists()
    }

    /// Reads the pty until `needle` turns up, and fails loudly with everything
    /// that did arrive when it does not.
    async fn expect(output: &mut mpsc::UnboundedReceiver<Vec<u8>>, needle: &str) -> String {
        let mut seen = String::new();
        let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
        while !seen.contains(needle) {
            let left = deadline.saturating_duration_since(tokio::time::Instant::now());
            if left.is_zero() {
                panic!("timed out waiting for {needle:?}; the pty said: {seen:?}");
            }
            match tokio::time::timeout(left, output.recv()).await {
                Ok(Some(bytes)) => seen.push_str(&String::from_utf8_lossy(&bytes)),
                Ok(None) => panic!("the pty closed before {needle:?}; it said: {seen:?}"),
                Err(_) => panic!("timed out waiting for {needle:?}; the pty said: {seen:?}"),
            }
        }
        seen
    }

    #[tokio::test]
    async fn a_shell_takes_input_gives_output_and_starts_in_the_root() {
        let (root, config) = config("echo");
        let (mut session, mut output) = Session::spawn(&config, 80, 24).expect("spawn");
        let pid = session.pid.expect("a pid");
        assert!(alive(pid), "the shell is a real process");

        session
            .input
            .send(b"echo crow-pty-marker\n".to_vec())
            .unwrap();
        let seen = expect(&mut output, "crow-pty-marker").await;
        assert!(
            seen.contains("echo crow-pty-marker"),
            "a pty echoes what it is given: {seen:?}"
        );

        session.input.send(b"pwd\n".to_vec()).unwrap();
        let cwd = root.canonicalize().unwrap();
        expect(&mut output, &cwd.display().to_string()).await;

        // The shell sees a terminal, which is the whole point of a pty.
        session
            .input
            .send(b"test -t 1 && echo crow-pty-isatty\n".to_vec())
            .unwrap();
        expect(&mut output, "crow-pty-isatty").await;

        let status = session.reap().await.expect("an exit status");
        assert!(status.signal().is_some(), "killed, not exited: {status:?}");
        for _ in 0..100 {
            if !alive(pid) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        assert!(!alive(pid), "reap leaves no process behind");
    }

    #[tokio::test]
    async fn resize_reaches_the_kernel() {
        let (_root, config) = config("resize");
        let (session, mut output) = Session::spawn(&config, 80, 24).expect("spawn");

        session.input.send(b"stty size\n".to_vec()).unwrap();
        expect(&mut output, "24 80").await;

        resize(&session.master, 132, 43).expect("resize");
        session.input.send(b"stty size\n".to_vec()).unwrap();
        expect(&mut output, "43 132").await;
    }

    #[tokio::test]
    async fn a_shell_that_exits_closes_the_output_and_reports_its_code() {
        let (_root, config) = config("exit");
        let (mut session, mut output) = Session::spawn(&config, 80, 24).expect("spawn");
        let pid = session.pid.expect("a pid");
        session.input.send(b"exit 3\n".to_vec()).unwrap();

        // EOF on the pty closes the channel: that is how the server learns the
        // shell is gone without polling the child.
        while output.recv().await.is_some() {}
        let status = session.reap().await.expect("an exit status");
        assert_eq!(status.exit_code(), 3);
        assert!(status.signal().is_none(), "{status:?}");
        assert!(!alive(pid), "the shell is gone");
    }

    #[tokio::test]
    async fn dropping_a_session_kills_its_shell() {
        let (_root, config) = config("drop");
        let pid = {
            let (session, _output) = Session::spawn(&config, 80, 24).expect("spawn");
            let pid = session.pid.expect("a pid");
            assert!(alive(pid));
            pid
            // session drops here without a reap: the socket vanished mid-turn.
        };
        for _ in 0..100 {
            if !alive(pid) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        assert!(!alive(pid), "a dropped session must not leak a shell");
    }

    #[tokio::test]
    async fn spawn_reports_a_shell_that_is_not_there() {
        let fs = crate::ws::Fs::new(std::env::temp_dir()).expect("fs state");
        let config = Config::new(fs, Some("/nonexistent/shell".to_string()));
        let err = match Session::spawn(&config, 80, 24) {
            Ok(_) => panic!("a shell that is not there should not spawn"),
            Err(e) => e.to_string(),
        };
        assert!(err.contains("spawn"), "{err}");
    }

    #[test]
    fn config_falls_back_to_the_environment_then_bash() {
        let fs = crate::ws::Fs::new("/tmp".into()).expect("fs state");
        let explicit = Config::new(fs.clone(), Some("/bin/zsh".to_string()));
        assert_eq!(explicit.shell(), "/bin/zsh");
        let from_env = Config::new(fs, None);
        let expected = std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
        assert_eq!(from_env.shell(), expected);
    }
}

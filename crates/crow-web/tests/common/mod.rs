//! Shared harness for the socket-level tests: spawn the shipped binary against
//! a throwaway root and learn the port it actually bound.
//!
//! `--port 0` plus reading the address off stdout is the race-free way to do
//! this. The obvious alternative — bind a probe listener, read its port, drop
//! it, hand the port to the server — lets two tests in one process (or two test
//! binaries running in parallel) pick the same port; one server then exits
//! while the other's probe reports "listening", and a later connect is refused.
use std::io::{BufRead, BufReader, Read};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};

pub struct Server {
    child: Child,
    pub port: u16,
    pub root: PathBuf,
}

impl Server {
    /// The websocket url for one of the server's endpoints.
    pub fn ws(&self, path: &str) -> String {
        format!("ws://127.0.0.1:{}{path}", self.port)
    }

    pub fn disk(&self, rel: &str) -> Option<String> {
        std::fs::read_to_string(self.root.join(rel)).ok()
    }

    pub fn exists(&self, rel: &str) -> bool {
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

pub fn spawn(name: &str, extra_args: &[&str]) -> Server {
    let root = temp_root(name);
    let mut child = Command::new(env!("CARGO_BIN_EXE_crow-web"))
        .args(["--port", "0", "--root"])
        .arg(&root)
        .args(extra_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .expect("spawn crow-web");
    let stdout = child.stdout.take().expect("piped stdout");
    let port = bound_port(stdout);
    Server { child, port, root }
}

/// Reads the startup line and pulls the port out of the address in it.
fn bound_port(stdout: impl Read) -> u16 {
    for line in BufReader::new(stdout).lines() {
        let line = line.expect("read crow-web's stdout");
        let Some(url) = line.split("http://").nth(1) else {
            continue;
        };
        let Some(authority) = url.split_whitespace().next() else {
            continue;
        };
        if let Some((_, port)) = authority.rsplit_once(':') {
            return port.parse().expect("a port in the startup line");
        }
    }
    panic!("crow-web exited before it printed its address");
}

/// Hand-rolled, like the unit tests: no tempfile dev-dependency in this repo.
pub fn temp_root(name: &str) -> PathBuf {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir().join(format!(
        "crow-web-{name}-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed),
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("create temp root");
    dir
}

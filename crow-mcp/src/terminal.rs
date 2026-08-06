//! Persistent PTY-backed terminal — ported from sandbox.
//!
//! Sentinel-based completion detection, ANSI stripping, streaming chunks.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::io::{AsRawFd, FromRawFd};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use nix::fcntl::{FcntlArg, OFlag};
use nix::pty::openpty;
use nix::sys::signal::{self, Signal};
use nix::sys::wait::WaitPidFlag;
use nix::unistd::{ForkResult, Pid};

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct TerminalParams {
    /// The command to execute in the persistent terminal
    command: String,
    /// Working directory (defaults to current directory)
    #[serde(skip_serializing_if = "Option::is_none")]
    cwd: Option<String>,
    /// Timeout in seconds (default 30)
    #[serde(skip_serializing_if = "Option::is_none")]
    timeout: Option<u64>,
}

#[tool_router(router = terminal_router, vis = "pub")]
impl CrowMcpServer {
    /// Execute a command in a persistent terminal session.
    ///
    /// Streams raw PTY bytes to the client while the command runs, as MCP
    /// progress notifications keyed by the request's progressToken (the agent
    /// forwards them as ACP terminal_output_chunk updates). The final result
    /// still arrives as one response: ANSI-stripped text for the LLM +
    /// raw_bytes_b64 for the ACP Terminal snapshot.
    #[tool(description = "Execute a bash command in a persistent terminal. State (env vars, cwd) persists across calls. Returns exit code and output.")]
    async fn terminal(
        &self,
        peer: rmcp::service::Peer<rmcp::RoleServer>,
        meta: rmcp::model::Meta,
        Parameters(params): Parameters<TerminalParams>,
    ) -> Result<CallToolResult, McpError> {
        let cwd = params.cwd.unwrap_or_else(|| {
            std::env::current_dir()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string()
        });
        let timeout = params.timeout.map(std::time::Duration::from_secs);
        let token = meta.get_progress_token();

        // PTY chunks → base64 progress notifications (message = data channel).
        let (chunk_tx, mut chunk_rx) = tokio::sync::mpsc::unbounded_channel::<(f64, String)>();
        let forwarder = tokio::spawn(async move {
            while let Some((progress, b64)) = chunk_rx.recv().await {
                let Some(token) = &token else { continue };
                let mut param =
                    rmcp::model::ProgressNotificationParam::new(token.clone(), progress);
                param.message = Some(b64);
                let _ = peer.notify_progress(param).await;
            }
        });

        // Terminal ops are blocking (PTY polling) — run on a blocking thread.
        // chunk_tx moves in; dropping it on return ends the forwarder.
        let result = {
            let state = self.state.clone();
            tokio::task::spawn_blocking(move || {
                let mut state = state.blocking_lock();
                let (term, rx) = state.terminal_mgr.get_or_create_with_rx(&cwd)?;
                term.execute_streaming(&params.command, timeout, rx, |total, chunk| {
                    let b64 = base64::Engine::encode(
                        &base64::engine::general_purpose::STANDARD,
                        chunk,
                    );
                    let _ = chunk_tx.send((total as f64, b64));
                })
            })
            .await
            .map_err(|e| McpError::internal_error(format!("task join error: {e}"), None))?
            .map_err(|e| McpError::internal_error(format!("terminal error: {e}"), None))?
        };
        let _ = forwarder.await;

        let output = serde_json::json!({
            "exit_code": result.exit_code,
            "output": result.stripped_text,
            "timed_out": result.timed_out,
            // Raw PTY bytes (ANSI intact) — react.rs lifts these into the ACP
            // Terminal schema and strips the field before the LLM sees it.
            "raw_bytes_b64": base64::Engine::encode(
                &base64::engine::general_purpose::STANDARD,
                &result.raw_bytes,
            ),
        });

        Ok(CallToolResult::success(vec![ContentBlock::text(
            serde_json::to_string_pretty(&output).unwrap(),
        )]))
    }
}

const SENTINEL: &str = "__CROW_DONE_";
const POLL_INTERVAL: Duration = Duration::from_millis(50);
const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);
/// Bytes held back from the live stream so the sentinel can never leak to the
/// client (sentinel pattern is ~27 bytes; hold a bit more to be safe).
const SENTINEL_HOLD: usize = 48;

/// Result of a command execution.
#[derive(Debug)]
#[allow(dead_code)]
pub struct CommandResult {
    /// Raw PTY bytes (ANSI colors intact) — base64 encode for ACP TerminalUpdate.output
    pub raw_bytes: Vec<u8>,
    /// ANSI-stripped text — for ACP ToolCallUpdate.raw_output (what the LLM sees)
    pub stripped_text: String,
    /// Exit code from the sentinel
    pub exit_code: i32,
    /// Whether the command timed out
    pub timed_out: bool,
}

/// A persistent PTY-backed terminal session.
#[allow(dead_code)]
pub struct PersistentTerminal {
    #[allow(dead_code)]
    terminal_id: String,
    master_fd: std::os::unix::io::RawFd,
    child_pid: Pid,
    buffer: Arc<Mutex<Vec<u8>>>,
    #[allow(dead_code)]
    cwd: String,
    /// Streaming channel — chunks sent here as they arrive
    chunk_tx: std::sync::mpsc::Sender<Vec<u8>>,
}

impl PersistentTerminal {
    pub fn new(
        terminal_id: &str,
        cwd: &str,
    ) -> anyhow::Result<(Self, std::sync::mpsc::Receiver<Vec<u8>>)> {
        let pty = openpty(None, None)?;

        // Set non-blocking on master
        let flags = nix::fcntl::fcntl(&pty.master, FcntlArg::F_GETFL)?;
        let mut oflags = OFlag::from_bits_truncate(flags);
        oflags.insert(OFlag::O_NONBLOCK);
        nix::fcntl::fcntl(&pty.master, FcntlArg::F_SETFL(oflags))?;

        let master_fd = pty.master.as_raw_fd();
        let slave_fd = pty.slave.as_raw_fd();

        let child_pid = match unsafe { nix::unistd::fork() } {
            Ok(ForkResult::Child) => {
                nix::unistd::setsid().expect("setsid");
                unsafe {
                    libc::ioctl(slave_fd, libc::TIOCSCTTY as _, 0);
                    libc::dup2(slave_fd, 0);
                    libc::dup2(slave_fd, 1);
                    libc::dup2(slave_fd, 2);
                }
                std::env::set_current_dir(cwd).expect("chdir");
                std::env::set_var("TERM", "xterm-256color");
                let err = nix::unistd::execvp(
                    &std::ffi::CString::new("bash").unwrap(),
                    &[std::ffi::CString::new("bash").unwrap()],
                );
                eprintln!("exec failed: {err:?}");
                std::process::exit(127);
            }
            Ok(ForkResult::Parent { child }) => child,
            Err(e) => anyhow::bail!("fork failed: {e}"),
        };

        std::mem::forget(pty.master);
        std::mem::forget(pty.slave);

        let buffer = Arc::new(Mutex::new(Vec::new()));
        let (chunk_tx, chunk_rx) = std::sync::mpsc::channel();

        let reader_buf = buffer.clone();
        let reader_tx = chunk_tx.clone();
        std::thread::spawn(move || {
            let mut file = unsafe { std::fs::File::from_raw_fd(master_fd) };
            let mut tmp = [0u8; 8192];
            loop {
                match file.read(&mut tmp) {
                    Ok(0) => break,
                    Ok(n) => {
                        let chunk = tmp[..n].to_vec();
                        reader_buf.lock().unwrap().extend_from_slice(&chunk);
                        let _ = reader_tx.send(chunk);
                    }
                    Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(10));
                    }
                    Err(_) => break,
                }
            }
            std::mem::forget(file);
        });

        // Wait for bash to start, clear startup output
        std::thread::sleep(Duration::from_millis(300));
        buffer.lock().unwrap().clear();

        Ok((
            Self {
                terminal_id: terminal_id.to_string(),
                master_fd,
                child_pid,
                buffer,
                cwd: cwd.to_string(),
                chunk_tx,
            },
            chunk_rx,
        ))
    }

    /// Execute a command, streaming raw PTY chunks through `on_chunk` as they
    /// arrive (cumulative byte count, new bytes). The command echo line and
    /// the sentinel are hidden from the stream. Same completion semantics as
    /// `execute`; there is deliberately NO idle-output kill — long quiet
    /// commands (grep, cargo build) are protected by the overall timeout only.
    pub fn execute_streaming(
        &self,
        command: &str,
        timeout: Option<Duration>,
        rx: &std::sync::mpsc::Receiver<Vec<u8>>,
        mut on_chunk: impl FnMut(u64, &[u8]),
    ) -> anyhow::Result<CommandResult> {
        let timeout = timeout.unwrap_or(DEFAULT_TIMEOUT);
        while rx.try_recv().is_ok() {} // drain stale chunks from earlier commands
        self.buffer.lock().unwrap().clear();

        let full_cmd = format!("{command}; echo \"{SENTINEL}$?{SENTINEL}\"\n");
        self.write_pty(full_cmd.as_bytes())?;

        let start = Instant::now();
        let mut acc: Vec<u8> = Vec::new();
        let mut emitted: usize = 0;
        let mut echo_end: Option<usize> = None;

        loop {
            match rx.recv_timeout(POLL_INTERVAL) {
                Ok(chunk) => acc.extend_from_slice(&chunk),
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                    let raw_start = acc
                        .iter()
                        .position(|&b| b == b'\n')
                        .map(|p| p + 1)
                        .unwrap_or(0);
                    let raw = acc[raw_start..].to_vec();
                    return Ok(CommandResult {
                        stripped_text: format!(
                            "{}\n\n[terminal disconnected]",
                            strip_ansi(&String::from_utf8_lossy(&raw))
                        ),
                        raw_bytes: raw,
                        exit_code: -1,
                        timed_out: false,
                    });
                }
            }

            let text = String::from_utf8_lossy(&acc);
            if let Some(pos) = find_sentinel(&text) {
                // Raw starts after the PTY echo of the input line — the echo
                // contains the sentinel text and must never leak (stream or
                // snapshot).
                let raw_start = acc
                    .iter()
                    .position(|&b| b == b'\n')
                    .map(|p| p + 1)
                    .unwrap_or(0);
                // Flush everything before the sentinel, skipping the echo.
                // (Fast commands complete before the incremental emission
                // runs, so the final flush must apply the same skip.)
                let lo = emitted.max(raw_start);
                if pos > lo {
                    on_chunk(pos as u64, &acc[lo..pos]);
                }
                let after_prefix = &text[pos + SENTINEL.len()..];
                let end_pos = after_prefix.find(SENTINEL).unwrap();
                let exit_code: i32 = after_prefix[..end_pos].trim().parse().unwrap_or(-1);
                let raw = acc[raw_start..pos].to_vec();
                let output_text = String::from_utf8_lossy(&raw).to_string();
                return Ok(CommandResult {
                    raw_bytes: raw,
                    stripped_text: strip_ansi(&output_text),
                    exit_code,
                    timed_out: false,
                });
            }

            if start.elapsed() >= timeout {
                let safe = acc.len().saturating_sub(SENTINEL_HOLD);
                if safe > emitted {
                    on_chunk(safe as u64, &acc[emitted..safe]);
                }
                let raw_start = acc
                    .iter()
                    .position(|&b| b == b'\n')
                    .map(|p| p + 1)
                    .unwrap_or(0);
                let raw = acc[raw_start..].to_vec();
                return Ok(CommandResult {
                    stripped_text: format!(
                        "{}\n\n[Command timed out after {:.0}s]",
                        strip_ansi(&String::from_utf8_lossy(&raw)),
                        timeout.as_secs_f64()
                    ),
                    raw_bytes: raw,
                    exit_code: -1,
                    timed_out: true,
                });
            }

            // Stream new bytes: skip the command echo line, hold back a tail so
            // a sentinel split across chunks can never leak.
            if echo_end.is_none() {
                echo_end = acc.iter().position(|&b| b == b'\n').map(|p| p + 1);
            }
            if let Some(ee) = echo_end {
                let safe = acc.len().saturating_sub(SENTINEL_HOLD);
                let lo = emitted.max(ee);
                if safe > lo {
                    on_chunk(safe as u64, &acc[lo..safe]);
                    emitted = safe;
                }
            }
        }
    }

    fn write_pty(&self, data: &[u8]) -> anyhow::Result<()> {
        let mut file = unsafe { std::fs::File::from_raw_fd(self.master_fd) };
        file.write_all(data)?;
        std::mem::forget(file);
        Ok(())
    }

    #[allow(dead_code)]
    pub fn interrupt(&self) {
        let _ = signal::kill(self.child_pid, Signal::SIGINT);
    }

    fn close(&self) {
        let _ = signal::kill(self.child_pid, Signal::SIGTERM);
        std::thread::sleep(Duration::from_millis(100));
        let _ = nix::sys::wait::waitpid(self.child_pid, Some(WaitPidFlag::WNOHANG));
    }
}

impl Drop for PersistentTerminal {
    fn drop(&mut self) {
        self.close();
    }
}

/// Find a REAL sentinel — `__CROW_DONE_<digits>__`. Skips the command echo.
fn find_sentinel(text: &str) -> Option<usize> {
    let mut search_from = 0;
    while let Some(rel) = text[search_from..].find(SENTINEL) {
        let pos = search_from + rel;
        let after = &text[pos + SENTINEL.len()..];
        let digits: String = after.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !digits.is_empty() && after[digits.len()..].starts_with(SENTINEL) {
            return Some(pos);
        }
        search_from = pos + SENTINEL.len();
    }
    None
}

/// Strip ANSI escape sequences from text.
pub fn strip_ansi(text: &str) -> String {
    let stripped = strip_ansi_escapes::strip(text);
    String::from_utf8_lossy(&stripped)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .trim()
        .to_string()
}

/// Remove the command echo line from PTY output.
// ---------------------------------------------------------------------------
// Session manager
// ---------------------------------------------------------------------------

pub struct TerminalManager {
    terminals: HashMap<String, PersistentTerminal>,
    chunk_rxs: HashMap<String, std::sync::mpsc::Receiver<Vec<u8>>>,
    counter: u64,
}

impl TerminalManager {
    pub fn new() -> Self {
        Self {
            terminals: HashMap::new(),
            chunk_rxs: HashMap::new(),
            counter: 0,
        }
    }

    /// Get (or create) the terminal for `cwd` together with its live chunk
    /// receiver — used by `execute_streaming` to stream PTY bytes out.
    pub fn get_or_create_with_rx(
        &mut self,
        cwd: &str,
    ) -> anyhow::Result<(&PersistentTerminal, &std::sync::mpsc::Receiver<Vec<u8>>)> {
        let key = cwd.to_string();
        if !self.terminals.contains_key(&key) {
            self.counter += 1;
            let id = format!("term_{:03}", self.counter);
            tracing::info!("creating terminal {id} in {cwd}");
            let (term, rx) = PersistentTerminal::new(&id, cwd)?;
            self.chunk_rxs.insert(key.clone(), rx);
            self.terminals.insert(key.clone(), term);
        }
        let term = self.terminals.get(&key).unwrap();
        let rx = self.chunk_rxs.get(&key).unwrap();
        Ok((term, rx))
    }

}

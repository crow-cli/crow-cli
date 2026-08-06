//! Persistent terminal sandbox — PTY + sentinel-based completion detection.
//!
//! No alacritty, no VT emulation. Just a PTY, raw byte capture,
//! ANSI stripping, and a sentinel for command completion.
//!
//! Output model (maps to ACP v2):
//! - raw bytes (base64) → TerminalUpdate.output / TerminalOutputChunk  (client renders)
//! - stripped text      → ToolCallUpdate.raw_output                    (LLM reads)

use std::collections::HashMap;
use std::io::{Read, Write};
use std::os::unix::io::{AsRawFd, FromRawFd};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use base64::Engine;
use nix::fcntl::{FcntlArg, OFlag};
use nix::pty::openpty;
use nix::sys::signal::{self, Signal};
use nix::sys::wait::WaitPidFlag;
use nix::unistd::{ForkResult, Pid};

const SENTINEL: &str = "__CROW_DONE_";
const POLL_INTERVAL: Duration = Duration::from_millis(50);
const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30);
const NO_CHANGE_TIMEOUT: Duration = Duration::from_secs(10);

/// Result of a command execution.
#[derive(Debug)]
#[allow(dead_code)]
struct CommandResult {
    /// Raw PTY bytes (ANSI colors intact) — base64 encode for ACP TerminalUpdate.output
    raw_bytes: Vec<u8>,
    /// ANSI-stripped text — for ACP ToolCallUpdate.raw_output (what the LLM sees)
    stripped_text: String,
    /// Exit code from the sentinel
    exit_code: i32,
    /// Whether the command timed out
    timed_out: bool,
}

/// A persistent PTY-backed terminal session.
#[allow(dead_code)]
struct PersistentTerminal {
    terminal_id: String,
    master_fd: std::os::unix::io::RawFd,
    child_pid: Pid,
    /// Raw bytes accumulated by the reader thread
    buffer: Arc<Mutex<Vec<u8>>>,
    cwd: String,
    /// Streaming channel — chunks sent here as they arrive (for TerminalOutputChunk)
    chunk_tx: std::sync::mpsc::Sender<Vec<u8>>,
}

impl PersistentTerminal {
    fn new(terminal_id: &str, cwd: &str) -> anyhow::Result<(Self, std::sync::mpsc::Receiver<Vec<u8>>)> {
        let pty = openpty(None, None)?;

        // Set non-blocking on master
        let flags = nix::fcntl::fcntl(&pty.master, FcntlArg::F_GETFL)?;
        let mut oflags = OFlag::from_bits_truncate(flags);
        oflags.insert(OFlag::O_NONBLOCK);
        nix::fcntl::fcntl(&pty.master, FcntlArg::F_SETFL(oflags))?;

        let master_fd = pty.master.as_raw_fd();
        let slave_fd = pty.slave.as_raw_fd();

        // Fork child process
        let child_pid = match unsafe { nix::unistd::fork() } {
            Ok(ForkResult::Child) => {
                // Child: set up session and exec bash
                nix::unistd::setsid().expect("setsid");

                // Set controlling terminal
                unsafe {
                    libc::ioctl(slave_fd, libc::TIOCSCTTY as _, 0);
                }

                // Dup slave to stdin/stdout/stderr
                unsafe {
                    libc::dup2(slave_fd, 0);
                    libc::dup2(slave_fd, 1);
                    libc::dup2(slave_fd, 2);
                }

                std::env::set_current_dir(cwd).expect("chdir");
                std::env::set_var("TERM", "xterm-256color");

                // Exec bash
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

        // Parent: keep master fd, forget both so they stay open
        std::mem::forget(pty.master);
        std::mem::forget(pty.slave);

        let buffer = Arc::new(Mutex::new(Vec::new()));
        let (chunk_tx, chunk_rx) = std::sync::mpsc::channel();

        // Start reader thread — appends to buffer AND streams chunks
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
            std::mem::forget(file); // don't close fd on thread exit
        });

        // Wait for bash to start
        std::thread::sleep(Duration::from_millis(300));

        // Clear startup output
        buffer.lock().unwrap().clear();

        Ok((Self {
            terminal_id: terminal_id.to_string(),
            master_fd,
            child_pid,
            buffer,
            cwd: cwd.to_string(),
            chunk_tx,
        }, chunk_rx))
    }

    /// Execute a command and wait for completion.
    ///
    /// Uses a sentinel: `command; echo "__CROW_DONE_$?__"`
    /// Watches for the sentinel in the output stream.
    fn execute(
        &self,
        command: &str,
        timeout: Option<Duration>,
    ) -> anyhow::Result<CommandResult> {
        let timeout = timeout.unwrap_or(DEFAULT_TIMEOUT);

        // Clear buffer
        self.buffer.lock().unwrap().clear();

        // Send command with sentinel
        let full_cmd = format!("{command}; echo \"{SENTINEL}$?{SENTINEL}\"\n");
        self.write_pty(full_cmd.as_bytes())?;

        let start = Instant::now();
        let mut last_change = start;
        let mut last_len = 0;

        // Poll for sentinel
        loop {
            std::thread::sleep(POLL_INTERVAL);

            let buf = self.buffer.lock().unwrap().clone();
            let text = String::from_utf8_lossy(&buf);

            // Check for sentinel — must have digits between the markers
            // (the command echo contains literal "$?", only the real output has a number)
            if let Some(pos) = find_sentinel(&text) {
                let after_prefix = &text[pos + SENTINEL.len()..];
                let end_pos = after_prefix.find(SENTINEL).unwrap();
                let exit_str = &after_prefix[..end_pos];
                let exit_code: i32 = exit_str.trim().parse().unwrap_or(-1);

                // Extract output: everything before the sentinel line
                let output_text = &text[..pos];

                // Strip the command echo (first line)
                let output_text = strip_command_echo(output_text, command);

                // Get raw bytes for the output portion
                let raw_output = &buf[..pos];

                return Ok(CommandResult {
                    raw_bytes: raw_output.to_vec(),
                    stripped_text: strip_ansi(&output_text),
                    exit_code,
                    timed_out: false,
                });
            }

            // Hard timeout
            if start.elapsed() >= timeout {
                let raw = self.buffer.lock().unwrap().clone();
                return Ok(CommandResult {
                    stripped_text: format!("{}\n\n[Command timed out after {:.0}s]",
                        strip_ansi(&String::from_utf8_lossy(&raw)), timeout.as_secs_f64()),
                    raw_bytes: raw,
                    exit_code: -1,
                    timed_out: true,
                });
            }

            // Soft timeout (no output change)
            let current_len = buf.len();
            if current_len != last_len {
                last_change = Instant::now();
                last_len = current_len;
            } else if last_change.elapsed() >= NO_CHANGE_TIMEOUT {
                let raw = self.buffer.lock().unwrap().clone();
                return Ok(CommandResult {
                    stripped_text: format!("{}\n\n[No output change for {:.0}s]",
                        strip_ansi(&String::from_utf8_lossy(&raw)),
                        NO_CHANGE_TIMEOUT.as_secs_f64()),
                    raw_bytes: raw,
                    exit_code: -1,
                    timed_out: true,
                });
            }
        }
    }

    fn write_pty(&self, data: &[u8]) -> anyhow::Result<()> {
        use std::os::unix::io::FromRawFd;
        let mut file = unsafe { std::fs::File::from_raw_fd(self.master_fd) };
        file.write_all(data)?;
        std::mem::forget(file);
        Ok(())
    }

    #[allow(dead_code)]
    fn interrupt(&self) {
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

/// Find a REAL sentinel in the output — `__CROW_DONE_<digits>__`.
/// Skips the command echo which contains the literal `$?` (not digits).
fn find_sentinel(text: &str) -> Option<usize> {
    let mut search_from = 0;
    while let Some(rel) = text[search_from..].find(SENTINEL) {
        let pos = search_from + rel;
        let after = &text[pos + SENTINEL.len()..];
        // Must be followed by digits then the closing sentinel
        let digits: String = after.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !digits.is_empty() && after[digits.len()..].starts_with(SENTINEL) {
            return Some(pos);
        }
        search_from = pos + SENTINEL.len();
    }
    None
}

/// Strip ANSI escape sequences from text.
fn strip_ansi(text: &str) -> String {
    let stripped = strip_ansi_escapes::strip(text);
    String::from_utf8_lossy(&stripped)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .trim()
        .to_string()
}

/// Remove the command echo line from PTY output.
/// The PTY always echoes the full input line first — skip it.
fn strip_command_echo(output: &str, _command: &str) -> String {
    // Skip past the first newline (the echoed input line)
    match output.find('\n') {
        Some(pos) => output[pos + 1..].to_string(),
        None => String::new(),
    }
}

// ---------------------------------------------------------------------------
// Session manager: terminal_id → PersistentTerminal
// ---------------------------------------------------------------------------

struct TerminalManager {
    terminals: HashMap<String, PersistentTerminal>,
    /// Chunk receivers — one per terminal, for streaming TerminalOutputChunk
    chunk_rxs: HashMap<String, std::sync::mpsc::Receiver<Vec<u8>>>,
    counter: u64,
}

impl TerminalManager {
    fn new() -> Self {
        Self { terminals: HashMap::new(), chunk_rxs: HashMap::new(), counter: 0 }
    }

    fn get_or_create(&mut self, cwd: &str) -> anyhow::Result<&PersistentTerminal> {
        // For now, one terminal per cwd
        let key = cwd.to_string();
        if !self.terminals.contains_key(&key) {
            self.counter += 1;
            let id = format!("term_{:03}", self.counter);
            println!("[manager] creating terminal {id} in {cwd}");
            let (term, rx) = PersistentTerminal::new(&id, cwd)?;
            self.chunk_rxs.insert(key.clone(), rx);
            self.terminals.insert(key.clone(), term);
        }
        Ok(self.terminals.get(&key).unwrap())
    }

    /// Drain pending chunks for a terminal (non-blocking).
    /// In the real agent, each chunk becomes a TerminalOutputChunk notification.
    fn drain_chunks(&self, cwd: &str) -> Vec<Vec<u8>> {
        let mut chunks = Vec::new();
        if let Some(rx) = self.chunk_rxs.get(cwd) {
            while let Ok(chunk) = rx.try_recv() {
                chunks.push(chunk);
            }
        }
        chunks
    }
}

// ---------------------------------------------------------------------------
// Main: demonstrate the persistent terminal
// ---------------------------------------------------------------------------

fn main() -> anyhow::Result<()> {
    println!("=== Persistent Terminal Sandbox ===\n");

    let mut mgr = TerminalManager::new();
    let cwd = std::env::current_dir()?.to_string_lossy().to_string();

    // Test 1: Simple echo
    println!("--- Test 1: echo ---");
    let term = mgr.get_or_create(&cwd)?;
    let result = term.execute("echo hello_from_pty", None)?;
    println!("exit_code: {}", result.exit_code);
    println!("stripped: {:?}", result.stripped_text);
    println!("raw_b64:  {}", base64::engine::general_purpose::STANDARD.encode(&result.raw_bytes));
    assert_eq!(result.exit_code, 0);
    assert!(result.stripped_text.contains("hello_from_pty"));
    println!("✅ PASS\n");

    // Test 2: Multi-line output
    println!("--- Test 2: multi-line ---");
    let term = mgr.get_or_create(&cwd)?;
    let result = term.execute("echo line1; echo line2; echo line3", None)?;
    println!("exit_code: {}", result.exit_code);
    println!("stripped: {:?}", result.stripped_text);
    assert_eq!(result.exit_code, 0);
    assert!(result.stripped_text.contains("line1"));
    assert!(result.stripped_text.contains("line3"));
    println!("✅ PASS\n");

    // Test 3: Exit code propagation
    println!("--- Test 3: exit code ---");
    let term = mgr.get_or_create(&cwd)?;
    let result = term.execute("false", None)?;
    println!("exit_code: {}", result.exit_code);
    assert_eq!(result.exit_code, 1);
    let result = term.execute("true", None)?;
    println!("exit_code: {}", result.exit_code);
    assert_eq!(result.exit_code, 0);
    println!("✅ PASS\n");

    // Test 4: ANSI colors preserved in raw, stripped in text
    println!("--- Test 4: ANSI colors ---");
    let term = mgr.get_or_create(&cwd)?;
    let result = term.execute("echo -e '\\033[31mRED\\033[0m \\033[32mGREEN\\033[0m'", None)?;
    println!("stripped: {:?}", result.stripped_text);
    let raw_str = String::from_utf8_lossy(&result.raw_bytes);
    println!("raw has ANSI: {}", raw_str.contains("\x1b["));
    assert!(result.stripped_text.contains("RED"));
    assert!(!result.stripped_text.contains("\x1b["));
    assert!(raw_str.contains("\x1b[")); // raw preserves ANSI
    println!("✅ PASS\n");

    // Test 5: Persistence — state carries across calls
    println!("--- Test 5: persistence ---");
    let term = mgr.get_or_create(&cwd)?;
    term.execute("export CROW_TEST_VAR=persistent_value", None)?;
    let result = term.execute("echo $CROW_TEST_VAR", None)?;
    println!("stripped: {:?}", result.stripped_text);
    assert!(result.stripped_text.contains("persistent_value"));
    println!("✅ PASS\n");

    // Test 6: Working directory persists
    println!("--- Test 6: cwd persistence ---");
    let term = mgr.get_or_create(&cwd)?;
    term.execute("cd /tmp", None)?;
    let result = term.execute("pwd", None)?;
    println!("stripped: {:?}", result.stripped_text);
    assert!(result.stripped_text.contains("/tmp"));
    println!("✅ PASS\n");

    // Test 7: ACP v2 output structure demo
    println!("--- Test 7: ACP v2 output structure ---");
    let term = mgr.get_or_create(&cwd)?;
    let result = term.execute("ls -la /tmp | head -3", None)?;
    let b64 = base64::engine::general_purpose::STANDARD;

    // This is what goes to the CLIENT (TerminalUpdate.output.data)
    let terminal_output_data = b64.encode(&result.raw_bytes);
    // This is what goes to the LLM (ToolCallUpdate.raw_output)
    let llm_output = serde_json::json!({
        "exit_code": result.exit_code,
        "output": result.stripped_text,
    });

    println!("TerminalUpdate.output.data (b64, {} bytes): {}...",
        terminal_output_data.len(), &terminal_output_data[..60.min(terminal_output_data.len())]);
    println!("ToolCallUpdate.raw_output: {}", serde_json::to_string_pretty(&llm_output)?);
    println!("✅ PASS\n");

    // Test 8: Streaming chunks (TerminalOutputChunk simulation)
    println!("--- Test 8: streaming chunks ---");
    // Drain any leftover chunks from previous tests
    mgr.drain_chunks(&cwd);
    let term = mgr.get_or_create(&cwd)?;
    term.execute("echo stream1; sleep 0.1; echo stream2; sleep 0.1; echo stream3", None)?;
    let chunks = mgr.drain_chunks(&cwd);
    println!("received {} chunks", chunks.len());
    let all_streamed: Vec<u8> = chunks.iter().flatten().copied().collect();
    let streamed_text = strip_ansi(&String::from_utf8_lossy(&all_streamed));
    println!("streamed text: {:?}", streamed_text);
    assert!(chunks.len() >= 1, "should have at least 1 chunk");
    assert!(streamed_text.contains("stream1"));
    assert!(streamed_text.contains("stream3"));

    // Show what the ACP notifications would look like
    let b64 = base64::engine::general_purpose::STANDARD;
    for (i, chunk) in chunks.iter().enumerate() {
        println!("  TerminalOutputChunk[{}]: {} bytes → b64 len {}",
            i, chunk.len(), b64.encode(chunk).len());
    }
    println!("✅ PASS\n");

    println!("=== All tests passed ===");
    Ok(())
}

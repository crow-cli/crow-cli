//! shell: extracted verbatim from src/app.rs (Phase 1 split).

use super::*;
use std::io::{BufReader, Read, Write};
use std::sync::mpsc::Sender;
use std::time::Duration;
use crate::bus::AppEvent;

pub(crate) struct ShellRequest {
    pub(crate) id: u64,
    pub(crate) command: String,
}

pub(crate) struct ShellWorker {
    pub(crate) tx: Sender<ShellRequest>,
}

impl ShellWorker {
    pub(crate) fn spawn(cwd: String, app_tx: Sender<AppEvent>) -> Self {
        let (tx, rx) = std::sync::mpsc::channel::<ShellRequest>();
        std::thread::spawn(move || {
            let mut shell: Option<PersistentShell> = None;
            for request in rx {
                if shell.is_none() {
                    match PersistentShell::spawn(&cwd) {
                        Ok(started) => shell = Some(started),
                        Err(err) => {
                            let _ = app_tx.send(AppEvent::ShellDone {
                                id: request.id,
                                code: None,
                                output: format!("failed to start shell: {err}"),
                            });
                            continue;
                        }
                    }
                }

                let result = shell.as_mut().unwrap().run(request.id, &request.command);
                let (code, output, alive) = match result {
                    Ok(result) => result,
                    Err(err) => (None, format!("shell failed: {err}"), false),
                };
                if !alive {
                    shell = None;
                }
                let _ = app_tx.send(AppEvent::ShellDone {
                    id: request.id,
                    code,
                    output,
                });
            }
        });
        Self { tx }
    }

    pub(crate) fn send(&self, request: ShellRequest) -> Result<(), ShellRequest> {
        self.tx.send(request).map_err(|err| err.0)
    }
}

pub(crate) struct PersistentShell {
    pub(crate) child: std::process::Child,
    pub(crate) stdin: std::process::ChildStdin,
    pub(crate) stdout: BufReader<std::process::ChildStdout>,
    pub(crate) marker: String,
}

/// Silence deadline for one `!` command. A wedged command (or a closed
/// control fd) must not block the single-shell worker forever; on timeout
/// the shell is killed and the next request spawns a fresh one.
#[cfg(unix)]
pub(crate) const SHELL_SILENCE: Duration = Duration::from_secs(120);

/// Outcome of the marker wait.
#[cfg(unix)]
pub(crate) enum ShellRead {
    /// Marker found; carries the parsed exit status.
    Done(Option<i32>),
    /// Shell stdout closed.
    Eof,
    /// No output within `SHELL_SILENCE`.
    Silent,
}

impl PersistentShell {
    fn spawn(cwd: &str) -> std::io::Result<Self> {
        let mut child = std::process::Command::new("sh")
            .arg("-l")
            .arg("-s")
            .current_dir(cwd)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()?;
        let mut stdin = child.stdin.take().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::BrokenPipe, "shell stdin unavailable")
        })?;
        let stdout = child.stdout.take().ok_or_else(|| {
            std::io::Error::new(std::io::ErrorKind::BrokenPipe, "shell stdout unavailable")
        })?;
        // Keep a control fd independent from shell-level stdout redirects.
        stdin.write_all(b"exec 9>&1\n")?;
        stdin.flush()?;
        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            marker: format!("CROW_SHELL_{}_{}", std::process::id(), timestamp()),
        })
    }

    fn run(&mut self, id: u64, command: &str) -> std::io::Result<(Option<i32>, String, bool)> {
        let marker = format!("\x1e{}:{id}:", self.marker);
        // stdin from /dev/null: the persistent shell's stdin is the command
        // pipe itself, so a command that reads it (`!cat`, `!ssh …`) would
        // otherwise swallow the status/marker lines and hang the marker
        // wait forever.
        writeln!(self.stdin, "eval {} 2>&1 < /dev/null", shell_quote(command))?;
        writeln!(self.stdin, "__crow_term_shell_status=$?")?;
        writeln!(
            self.stdin,
            "command printf '\\036{}:{id}:%s\\037' \"$__crow_term_shell_status\" >&9",
            self.marker
        )?;
        self.stdin.flush()?;

        let mut captured = Vec::new();
        #[cfg(unix)]
        {
            match self.read_marker(&marker, &mut captured)? {
                ShellRead::Done(status) => return Ok((status, shell_output(captured), true)),
                ShellRead::Eof => {
                    let code = self.child.wait().ok().and_then(|status| status.code());
                    return Ok((code, shell_output(captured), false));
                }
                ShellRead::Silent => {
                    // No output within the deadline: the command is wedged
                    // (the single worker thread must never block forever).
                    // Kill the shell; the next `!` request spawns a fresh one.
                    let _ = self.child.kill();
                    let _ = self.child.wait();
                    return Ok((
                        None,
                        format!(
                            "command killed: no output for {}s — the next `!` restarts the shell",
                            SHELL_SILENCE.as_secs()
                        ),
                        false,
                    ));
                }
            }
        }
        #[cfg(not(unix))]
        {
            loop {
                let read = self.stdout.read_until(0x1f, &mut captured)?;
                if read == 0 {
                    let code = self.child.wait().ok().and_then(|status| status.code());
                    return Ok((code, shell_output(captured), false));
                }
                let Some(start) = find_bytes(&captured, marker.as_bytes()) else {
                    continue;
                };
                let status_start = start + marker.len();
                let Some(status_len) = captured[status_start..]
                    .iter()
                    .position(|byte| *byte == 0x1f)
                else {
                    continue;
                };
                let status =
                    std::str::from_utf8(&captured[status_start..status_start + status_len])
                        .ok()
                        .and_then(|value| value.parse::<i32>().ok());
                captured.truncate(start);
                return Ok((status, shell_output(captured), true));
            }
        }
    }

    /// Read stdout until the status marker arrives. Poll-based so the
    /// silence deadline can fire even though `BufReader` has no
    /// non-blocking mode; every byte of progress resets the deadline.
    #[cfg(unix)]
    fn read_marker(
        &mut self,
        marker: &str,
        captured: &mut Vec<u8>,
    ) -> std::io::Result<ShellRead> {
        use std::os::unix::io::AsRawFd;
        let fd = self.stdout.get_ref().as_raw_fd();
        let mut pollfd = [libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        }];
        let mut chunk = [0u8; 8192];
        let marker_bytes = marker.as_bytes();
        let timeout_ms = SHELL_SILENCE.as_millis().min(i32::MAX as u128) as i32;
        loop {
            let ready = unsafe { libc::poll(pollfd.as_mut_ptr(), 1, timeout_ms) };
            if ready < 0 {
                let err = std::io::Error::last_os_error();
                if err.kind() == std::io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(err);
            }
            if ready == 0 {
                return Ok(ShellRead::Silent);
            }
            if pollfd[0].revents & libc::POLLNVAL != 0 {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::BrokenPipe,
                    "shell stdout closed",
                ));
            }
            // POLLIN (and/or POLLHUP) — a read never blocks here.
            let read = self.stdout.read(&mut chunk)?;
            if read == 0 {
                return Ok(ShellRead::Eof);
            }
            captured.extend_from_slice(&chunk[..read]);
            let Some(start) = find_bytes(captured, marker_bytes) else {
                continue;
            };
            let status_start = start + marker_bytes.len();
            let Some(status_len) = captured[status_start..].iter().position(|b| *b == 0x1f) else {
                continue;
            };
            let status =
                std::str::from_utf8(&captured[status_start..status_start + status_len])
                    .ok()
                    .and_then(|value| value.parse::<i32>().ok());
            captured.truncate(start);
            return Ok(ShellRead::Done(status));
        }
    }
}

impl Drop for PersistentShell {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub(crate) fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\\"'\\\"'"))
}

pub(crate) fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

pub(crate) fn shell_output(bytes: Vec<u8>) -> String {
    let mut output = String::from_utf8_lossy(&bytes).into_owned();
    const LIMIT: usize = 16 * 1024;
    if output.len() > LIMIT {
        let mut cut = LIMIT;
        while cut > 0 && !output.is_char_boundary(cut) {
            cut -= 1;
        }
        output.truncate(cut);
        output.push_str("\n… (truncated)");
    }
    output
}

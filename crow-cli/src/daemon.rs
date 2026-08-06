//! Daemon lifecycle for agent servers declared in client_settings.yaml.
//!
//! Two backends, one interface: when a systemd user unit
//! (`~/.config/systemd/user/crow-<name>.service`) is installed via
//! `crow-cli daemon install`, start/stop/status route through systemd
//! (Restart=always, boot persistence with linger). Otherwise the classic
//! pidfile path: `{config_dir}/run/<name>.pid`, output appended to
//! `{config_dir}/logs/<name>.log`, detached spawn in its own process group,
//! stop is SIGTERM then SIGKILL after 5s. Routing is exclusive per daemon —
//! a unit-managed daemon never touches pidfile state.

use std::os::unix::process::CommandExt as _;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::client_settings::{AgentServerConfig, ClientSettings};

pub fn pid_file(config_dir: &Path, name: &str) -> PathBuf {
    config_dir.join("run").join(format!("{name}.pid"))
}

pub fn log_file(config_dir: &Path, name: &str) -> PathBuf {
    config_dir.join("logs").join(format!("{name}.log"))
}

/// Daemon logs rotate at 5 MB, keeping 4 generations (`<name>.log.1..4`,
/// oldest dropped) — ≤20 MB per daemon, both backends.
const LOG_MAX_BYTES: u64 = 5 * 1024 * 1024;
const LOG_GENERATIONS: u32 = 4;

fn rotate_log_at(base: &Path, max_bytes: u64, generations: u32) {
    let Ok(meta) = std::fs::metadata(base) else {
        return;
    };
    if meta.len() <= max_bytes {
        return;
    }
    let gen_path = |i: u32| PathBuf::from(format!("{}.{i}", base.display()));
    let _ = std::fs::remove_file(gen_path(generations));
    for i in (1..generations).rev() {
        let _ = std::fs::rename(gen_path(i), gen_path(i + 1));
    }
    let _ = std::fs::rename(base, gen_path(1));
}

/// Rotate before either backend starts appending.
fn rotate_log(config_dir: &Path, name: &str) {
    rotate_log_at(&log_file(config_dir, name), LOG_MAX_BYTES, LOG_GENERATIONS);
}

pub fn alive(pid: u32) -> bool {
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

// ---------------------------------------------------------------- systemd --

pub fn unit_name(name: &str) -> String {
    format!("crow-{name}.service")
}

pub fn unit_path(name: &str) -> PathBuf {
    dirs::home_dir()
        .expect("home dir")
        .join(".config/systemd/user")
        .join(unit_name(name))
}

pub fn unit_installed(name: &str) -> bool {
    unit_path(name).exists()
}

fn systemctl(args: &[&str]) -> anyhow::Result<String> {
    let out = std::process::Command::new("systemctl")
        .arg("--user")
        .args(args)
        .output()
        .map_err(|e| anyhow::anyhow!("systemctl: {e}"))?;
    if !out.status.success() {
        anyhow::bail!(
            "systemctl --user {}: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn systemd_main_pid(name: &str) -> Option<u32> {
    let pid: u32 = systemctl(&["show", "-p", "MainPID", "--value", &unit_name(name)])
        .ok()?
        .trim()
        .parse()
        .ok()?;
    (pid != 0).then_some(pid)
}

fn systemd_active_state(name: &str) -> Option<String> {
    systemctl(&["show", "-p", "ActiveState", "--value", &unit_name(name)]).ok()
}

/// Alive = MainPID running, or systemd (re)starting it (Restart=always blips
/// MainPID to 0 between crash-restarts).
fn systemd_unit_alive(name: &str) -> bool {
    systemd_main_pid(name).is_some()
        || matches!(
            systemd_active_state(name).as_deref(),
            Some("activating") | Some("active") | Some("reloading")
        )
}

/// systemd ExecStart quoting: pass plainly-safe strings through, wrap the
/// rest in double quotes with `\`, `"` and `$` escaped.
fn sh_quote(s: &str) -> String {
    if !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | ':' | '.' | '/' | '@' | ','))
    {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        if matches!(c, '"' | '\\' | '$') {
            out.push('\\');
        }
        out.push(c);
    }
    out.push('"');
    out
}

/// The user-unit file for a daemon (pure function — unit-tested).
pub fn unit_file(name: &str, config_dir: &Path, cfg: &AgentServerConfig) -> String {
    let mut s = format!(
        "[Unit]\nDescription=crow daemon: {name}\nAfter=network-online.target\n\n[Service]\n"
    );
    let cmd = Path::new(&cfg.command);
    if let Some(dir) = cmd.parent().filter(|p| !p.as_os_str().is_empty()) {
        s.push_str(&format!("WorkingDirectory={}\n", dir.display()));
    }
    let mut exec = sh_quote(&cfg.command);
    for a in &cfg.args {
        exec.push(' ');
        exec.push_str(&sh_quote(a));
    }
    s.push_str(&format!("ExecStart={exec}\n"));
    let mut keys: Vec<&String> = cfg.env.keys().collect();
    keys.sort();
    for k in keys {
        s.push_str(&format!("Environment=\"{k}={}\"\n", cfg.env[k]));
    }
    let log = log_file(config_dir, name);
    s.push_str(&format!(
        "Restart=always\nRestartSec=3\nStandardOutput=append:{log}\nStandardError=append:{log}\n\n[Install]\nWantedBy=default.target\n",
        log = log.display()
    ));
    s
}

fn warn_if_no_linger() {
    let Some(user) = std::env::var("USER").ok().filter(|u| !u.is_empty()) else {
        return;
    };
    let linger = std::process::Command::new("loginctl")
        .args(["show-user", &user, "-p", "Linger", "--value"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string());
    if linger.as_deref() == Some("no") {
        eprintln!("warning: linger is off — units stop at logout and won't start at boot.");
        eprintln!("         run once: sudo loginctl enable-linger {user}");
    }
}

/// Poll MainPID until systemd has the process up (≤30s).
fn wait_main_pid(config_dir: &Path, name: &str) -> anyhow::Result<u32> {
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        if let Some(pid) = systemd_main_pid(name) {
            return Ok(pid);
        }
        if Instant::now() > deadline {
            anyhow::bail!(
                "daemon '{name}' did not start under systemd within 30s (see {})",
                log_file(config_dir, name).display()
            );
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// TCP health poll on the declared port (≤30s); `alive` gates early exit.
fn wait_port(name: &str, port: u16, hint: &str, alive: &dyn Fn() -> bool) -> anyhow::Result<()> {
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        if !alive() {
            anyhow::bail!("daemon '{name}' exited during startup ({hint})");
        }
        if Instant::now() > deadline {
            anyhow::bail!("daemon '{name}' did not open port {port} within 30s");
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// Write the unit, enable + start it, wait for health. Idempotent: reinstall
/// rewrites the file and reloads.
pub fn install(config_dir: &Path, name: &str, cfg: &AgentServerConfig) -> anyhow::Result<u32> {
    if !unit_installed(name) {
        if let Some(port) = cfg.port {
            if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
                anyhow::bail!(
                    "port {port} is already in use — stop the other listener before installing '{name}'"
                );
            }
        }
    }
    std::fs::create_dir_all(config_dir.join("logs"))?;
    rotate_log(config_dir, name);
    let path = unit_path(name);
    std::fs::create_dir_all(path.parent().expect("unit dir"))?;
    std::fs::write(&path, unit_file(name, config_dir, cfg))?;
    systemctl(&["daemon-reload"])?;
    systemctl(&["enable", "--now", &unit_name(name)])?;
    warn_if_no_linger();
    let pid = wait_main_pid(config_dir, name)?;
    if let Some(port) = cfg.port {
        let hint = format!("see {}", log_file(config_dir, name).display());
        wait_port(name, port, &hint, &|| systemd_unit_alive(name))?;
    }
    Ok(pid)
}

/// Disable + remove the unit. Does not delete logs or pidfile leftovers.
pub fn uninstall(name: &str) -> anyhow::Result<()> {
    if !unit_installed(name) {
        anyhow::bail!("no systemd unit installed for '{name}'");
    }
    let _ = systemctl(&["disable", "--now", &unit_name(name)]);
    std::fs::remove_file(unit_path(name))?;
    systemctl(&["daemon-reload"])?;
    Ok(())
}

// ---------------------------------------------------------------- pidfile --

/// The recorded pid, when the process is actually alive. Unit-managed daemons
/// report systemd's MainPID instead.
pub fn running_pid(config_dir: &Path, name: &str) -> Option<u32> {
    if unit_installed(name) {
        return systemd_main_pid(name);
    }
    let pid: u32 = std::fs::read_to_string(pid_file(config_dir, name))
        .ok()?
        .trim()
        .parse()
        .ok()?;
    alive(pid).then_some(pid)
}

pub fn start(config_dir: &Path, name: &str, cfg: &AgentServerConfig) -> anyhow::Result<u32> {
    if unit_installed(name) {
        if let Some(pid) = systemd_main_pid(name) {
            anyhow::bail!("daemon '{name}' already running (systemd, pid {pid})");
        }
        rotate_log(config_dir, name);
        systemctl(&["start", &unit_name(name)])?;
        let pid = wait_main_pid(config_dir, name)?;
        if let Some(port) = cfg.port {
            let hint = format!("see {}", log_file(config_dir, name).display());
            wait_port(name, port, &hint, &|| systemd_unit_alive(name))?;
        }
        return Ok(pid);
    }
    if let Some(pid) = running_pid(config_dir, name) {
        anyhow::bail!("daemon '{name}' already running (pid {pid})");
    }
    std::fs::create_dir_all(config_dir.join("run"))?;
    std::fs::create_dir_all(config_dir.join("logs"))?;
    rotate_log(config_dir, name);
    let log_path = log_file(config_dir, name);
    let log = std::fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let err = log.try_clone()?;

    let mut cmd = std::process::Command::new(&cfg.command);
    cmd.args(&cfg.args)
        .envs(&cfg.env)
        .stdin(std::process::Stdio::null())
        .stdout(log)
        .stderr(err)
        .process_group(0);
    let child = cmd
        .spawn()
        .map_err(|e| anyhow::anyhow!("spawn '{}': {e}", cfg.command))?;
    let pid = child.id();
    std::fs::write(pid_file(config_dir, name), pid.to_string())?;

    // Health: TCP poll on the declared port, else a liveness grace check.
    if let Some(port) = cfg.port {
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
                break;
            }
            if !alive(pid) {
                anyhow::bail!(
                    "daemon '{name}' exited during startup (see {})",
                    log_path.display()
                );
            }
            if Instant::now() > deadline {
                anyhow::bail!("daemon '{name}' did not open port {port} within 30s");
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    } else {
        std::thread::sleep(Duration::from_millis(200));
        if !alive(pid) {
            anyhow::bail!(
                "daemon '{name}' exited during startup (see {})",
                log_path.display()
            );
        }
    }
    Ok(pid)
}

pub fn stop(config_dir: &Path, name: &str) -> anyhow::Result<()> {
    if unit_installed(name) {
        systemctl(&["stop", &unit_name(name)])?;
        return Ok(());
    }
    let Some(pid) = running_pid(config_dir, name) else {
        let _ = std::fs::remove_file(pid_file(config_dir, name));
        anyhow::bail!("daemon '{name}' is not running");
    };
    unsafe { libc::kill(pid as i32, libc::SIGTERM) };
    let deadline = Instant::now() + Duration::from_secs(5);
    while alive(pid) {
        if Instant::now() > deadline {
            unsafe { libc::kill(pid as i32, libc::SIGKILL) };
            break;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = std::fs::remove_file(pid_file(config_dir, name));
    Ok(())
}

/// Start the named daemon when it is not already up.
pub fn ensure_running(
    config_dir: &Path,
    settings: &ClientSettings,
    name: &str,
) -> anyhow::Result<()> {
    ensure_running_rec(config_dir, settings, name, &mut std::collections::HashSet::new())
}

/// Recursive: a daemon's own `requires:` are ensured first (crow → daemon →
/// memory). `start` waits for each port, so the chain comes up in order.
fn ensure_running_rec(
    config_dir: &Path,
    settings: &ClientSettings,
    name: &str,
    visited: &mut std::collections::HashSet<String>,
) -> anyhow::Result<()> {
    if running_pid(config_dir, name).is_some() {
        return Ok(());
    }
    if !visited.insert(name.to_string()) {
        anyhow::bail!("requires: cycle detected at '{name}'");
    }
    let cfg = settings
        .agent_servers
        .get(name)
        .ok_or_else(|| anyhow::anyhow!("daemon '{name}' not found in client_settings.yaml"))?;
    for r in &cfg.requires {
        ensure_running_rec(config_dir, settings, r, visited)?;
    }
    let pid = start(config_dir, name, cfg)?;
    eprintln!("daemon '{name}' started (pid {pid})");
    Ok(())
}

#[derive(serde::Serialize)]
pub struct Status {
    pub name: String,
    /// "systemd" when a unit is installed, else "pidfile".
    pub managed_by: &'static str,
    pub running: bool,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    /// Port daemons only: TCP connect succeeded.
    pub healthy: Option<bool>,
    pub log: PathBuf,
}

pub fn status(config_dir: &Path, name: &str, cfg: &AgentServerConfig) -> Status {
    let pid = running_pid(config_dir, name);
    Status {
        name: name.to_string(),
        managed_by: if unit_installed(name) {
            "systemd"
        } else {
            "pidfile"
        },
        running: pid.is_some(),
        pid,
        port: cfg.port,
        healthy: cfg
            .port
            .map(|p| std::net::TcpStream::connect(("127.0.0.1", p)).is_ok()),
        log: log_file(config_dir, name),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::client_settings::ConfigOptions;

    fn cfg(command: &str, args: &[&str], env: &[(&str, &str)], port: Option<u16>) -> AgentServerConfig {
        AgentServerConfig {
            kind: Some("custom".to_string()),
            command: command.to_string(),
            args: args.iter().map(|s| s.to_string()).collect(),
            env: env.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect(),
            default_config_options: ConfigOptions::default(),
            port,
            requires: vec![],
        }
    }

    #[test]
    fn unit_naming() {
        assert_eq!(unit_name("ollama-mv"), "crow-ollama-mv.service");
        assert!(unit_path("ollama-mv")
            .to_string_lossy()
            .ends_with(".config/systemd/user/crow-ollama-mv.service"));
    }

    #[test]
    fn unit_file_contents() {
        let c = cfg(
            "/home/thomas/src/crow-team/ollama/ollama",
            &["serve"],
            &[
                ("OLLAMA_HOST", "127.0.0.1:11392"),
                ("OLLAMA_MODELS", "/home/thomas/.local/share/ollama-mv-models"),
            ],
            Some(11392),
        );
        let u = unit_file("ollama-mv", Path::new("/home/thomas/.agents/crow"), &c);
        assert!(u.contains("Description=crow daemon: ollama-mv"));
        assert!(u.contains("WorkingDirectory=/home/thomas/src/crow-team/ollama\n"));
        assert!(u.contains("ExecStart=/home/thomas/src/crow-team/ollama/ollama serve\n"));
        assert!(u.contains("Environment=\"OLLAMA_HOST=127.0.0.1:11392\"\n"));
        assert!(u.contains("Environment=\"OLLAMA_MODELS=/home/thomas/.local/share/ollama-mv-models\"\n"));
        assert!(u.contains("Restart=always"));
        assert!(u.contains("RestartSec=3"));
        assert!(u.contains("StandardOutput=append:/home/thomas/.agents/crow/logs/ollama-mv.log"));
        assert!(u.contains("WantedBy=default.target"));
        // env keys emitted sorted for a deterministic, diffable unit file
        assert!(u.find("OLLAMA_HOST").unwrap() < u.find("OLLAMA_MODELS").unwrap());
    }

    #[test]
    fn sh_quote_rules() {
        assert_eq!(sh_quote("/usr/bin/ollama"), "/usr/bin/ollama");
        assert_eq!(sh_quote("serve"), "serve");
        assert_eq!(sh_quote("--port 8080"), "\"--port 8080\"");
        assert_eq!(sh_quote("a\"b"), "\"a\\\"b\"");
        assert_eq!(sh_quote("$HOME/x"), "\"\\$HOME/x\"");
    }

    #[test]
    fn log_rotation() {
        let dir = std::env::temp_dir().join(format!("crow-rotate-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let log = dir.join("d.log");

        // under the cap: untouched
        std::fs::write(&log, "small").unwrap();
        rotate_log_at(&log, 10, 2);
        assert!(log.exists());

        // over the cap: shifts generations, drops the oldest
        std::fs::write(&log, "generation-A-over-cap").unwrap();
        rotate_log_at(&log, 10, 2);
        assert!(!log.exists());
        assert_eq!(std::fs::read_to_string(dir.join("d.log.1")).unwrap(), "generation-A-over-cap");

        std::fs::write(&log, "generation-B-over-cap").unwrap();
        rotate_log_at(&log, 10, 2);
        assert_eq!(std::fs::read_to_string(dir.join("d.log.1")).unwrap(), "generation-B-over-cap");
        assert_eq!(std::fs::read_to_string(dir.join("d.log.2")).unwrap(), "generation-A-over-cap");

        std::fs::write(&log, "generation-C-over-cap").unwrap();
        rotate_log_at(&log, 10, 2);
        assert_eq!(std::fs::read_to_string(dir.join("d.log.1")).unwrap(), "generation-C-over-cap");
        assert_eq!(std::fs::read_to_string(dir.join("d.log.2")).unwrap(), "generation-B-over-cap");
        assert!(!dir.join("d.log.3").exists()); // A dropped

        std::fs::remove_dir_all(&dir).unwrap();
    }
}

//! Shared launch/display configuration for the ACP client and demo painter.

use std::path::{Path, PathBuf};

/// `<root>/.agents/crow` — crow-cli's own config dir, now shared as this
/// client's home.
fn agents_crow(root: &str) -> PathBuf {
    Path::new(root).join(".agents").join("crow")
}

/// Resolve the crow home: an explicit `CROW_HOME`, then
/// the legacy `MARTTY_HOME` (so a pre-rebrand install keeps its data), then
/// `$DSH_HOME/.agents/crow`, then `~/.agents/crow`.
pub fn crow_home_from(
    crow_home: Option<&str>,
    martty_home: Option<&str>,
    dsh_home: Option<&str>,
    user_home: &str,
) -> PathBuf {
    for explicit in [crow_home, martty_home] {
        if let Some(home) = explicit.filter(|value| !value.is_empty()) {
            return PathBuf::from(home);
        }
    }
    if let Some(home) = dsh_home.filter(|value| !value.is_empty()) {
        return agents_crow(home);
    }
    agents_crow(user_home)
}

pub fn crow_home() -> PathBuf {
    let crow = std::env::var("CROW_HOME")
        .ok()
        .filter(|value| !value.is_empty());
    let martty = std::env::var("MARTTY_HOME").ok();
    let dsh = std::env::var("DSH_HOME").ok();
    let user = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    crow_home_from(crow.as_deref(), martty.as_deref(), dsh.as_deref(), &user)
}

pub fn default_session_root() -> PathBuf {
    crow_home().join("sessions")
}

pub fn settings_path(session_root: &str) -> PathBuf {
    if Path::new(session_root) == default_session_root() {
        crow_home().join("settings.json")
    } else {
        Path::new(session_root).join("settings.json")
    }
}

/// Settings files this build no longer writes but must still read, newest
/// first: the `~/.martty` home the rebrand left behind, then the older
/// `.dsh-tui` file. A custom `--session-root` has no `~/.martty` analogue —
/// its own `settings.json` is the current path — so only `.dsh-tui` applies.
pub fn legacy_settings_paths_from(
    session_root: &str,
    default_root: &Path,
    user_home: &str,
) -> Vec<PathBuf> {
    if Path::new(session_root) == default_root {
        vec![
            Path::new(user_home).join(".martty").join("settings.json"),
            Path::new(user_home)
                .join(".dsh-tui")
                .join("sessions")
                .join("dsh-tui-settings.json"),
        ]
    } else {
        vec![Path::new(session_root).join("dsh-tui-settings.json")]
    }
}

pub fn legacy_settings_paths(session_root: &str) -> Vec<PathBuf> {
    let user = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    legacy_settings_paths_from(session_root, &default_session_root(), &user)
}

/// How to reach the agent, and where this client keeps its own files.
///
/// Deliberately absent: provider, model, base URL, API key, token caps. An ACP
/// client does not own model configuration — the agent advertises the models it
/// can select from (`CatalogModel`) and reports the one a session runs
/// (`UiEvent::SessionModel`). Credentials belong to the agent too.
#[derive(Clone, Debug)]
pub struct RuntimeConfig {
    pub bin: String,
    pub workspace: String,
    pub session_root: String,
    /// `--session-id`: re-attach to this durable session at startup instead of
    /// creating one (`session/resume`, legacy `session/load`).
    pub startup_session: Option<String>,
}

impl RuntimeConfig {
    /// Environment for the spawned agent: where this client keeps its files,
    /// plus whatever the user's own harness recipe asks for. No credentials
    /// and no model route — the agent owns both.
    pub fn child_env(&self) -> Vec<(String, String)> {
        let mut env = vec![
            ("CROW_SESSION_ROOT".into(), self.session_root.clone()),
            ("CROW_CWD".into(), self.workspace.clone()),
        ];
        // A harness configured in settings.json may carry its own environment.
        // Apply it when that harness is the agent being spawned, and let it win
        // over the defaults above.
        if let Some(harness) = crate::harness::selected(&settings_path(&self.session_root)) {
            if harness.argv().join(" ") == self.bin {
                env.extend(harness.env);
            }
        }
        env
    }

    /// Spawn argv for the ACP agent (and Terminal Auth). `demo` falls back
    /// to `crow-cli acp2` so `/auth` still has a command to run.
    pub fn agent_argv(&self) -> Vec<String> {
        if self.bin.is_empty() || self.bin == "demo" {
            return vec!["crow-cli".into(), "acp2".into()];
        }
        self.bin.split_whitespace().map(str::to_string).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg(session_root: &str, bin: &str) -> RuntimeConfig {
        RuntimeConfig {
            bin: bin.into(),
            workspace: "/tmp".into(),
            session_root: session_root.into(),
            startup_session: None,
        }
    }

    fn root(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("crow-child-env-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn harness_env_applies_only_to_the_configured_agent() {
        let dir = root("harness");
        std::fs::write(
            dir.join("settings.json"),
            r#"{"harnesses":[{"id":"h","command":"/bin/agent","args":["acp"],"env":{"HARNESS_KEY":"yes"}}],"defaultHarness":"h"}"#,
        )
        .unwrap();
        let session_root = dir.to_string_lossy().into_owned();

        let matching = cfg(&session_root, "/bin/agent acp");
        assert!(
            matching
                .child_env()
                .contains(&("HARNESS_KEY".to_owned(), "yes".to_owned())),
            "the configured harness must supply its own environment"
        );

        let other = cfg(&session_root, "/bin/other-agent acp");
        assert!(
            !other
                .child_env()
                .iter()
                .any(|(key, _)| key == "HARNESS_KEY"),
            "an agent that is not the configured harness must not inherit its env"
        );
    }

    #[test]
    fn child_env_carries_no_provider_and_no_credentials() {
        let dir = root("no-credentials");
        std::fs::write(dir.join("settings.json"), "{}").unwrap();
        let env = cfg(&dir.to_string_lossy(), "/bin/agent acp").child_env();
        let keys: Vec<&str> = env.iter().map(|(key, _)| key.as_str()).collect();
        assert!(
            !keys.iter().any(|key| key.contains("API_KEY") || key.contains("BASE_URL")),
            "the client owns no credentials to hand an agent: {keys:?}"
        );
        assert!(
            !keys.iter().any(|key| key.contains("MODEL") || key.contains("PROVIDER")),
            "the client owns no model route to hand an agent: {keys:?}"
        );
    }
}

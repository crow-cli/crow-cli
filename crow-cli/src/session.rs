//! Agent session management — persistence layer for conversation state.
//!
//! Port of Python crow-cli/agent/session.py.
//! agent_id = "{session_id}-{agent_idx}" is the PK.

use std::path::Path;

use crate::config::Config;
use crate::coolname;
use crow_memory_sdk::MemoryClient;

/// Manages conversation state and persistence via LanceDB.
pub struct AgentSession {
    pub agent_id: String,
    pub session_id: String,
    pub agent_idx: i64,
    pub cwd: String,
    pub messages: Vec<serde_json::Value>,
    pub model_identifier: String,
    pub tools: serde_json::Value,
    #[allow(dead_code)]
    pub request_params: serde_json::Value,
    #[allow(dead_code)]
    pub prompt_id: String,
    #[allow(dead_code)]
    pub prompt_args: serde_json::Value,
}

impl AgentSession {
    /// Add a message to in-memory list AND persist to database.
    pub async fn add_message(
        &mut self,
        store: &MemoryClient,
        msg: serde_json::Value,
        usage: Option<serde_json::Value>,
    ) {
        self.messages.push(msg.clone());
        if let Err(e) = store
            .add_message(&self.agent_id, &msg, usage.as_ref())
            .await
        {
            tracing::warn!("failed to persist message: {e}");
        }
    }

    /// Build and persist an assistant response.
    pub async fn add_assistant_response(
        &mut self,
        store: &MemoryClient,
        thinking: &[String],
        content: &[String],
        tool_call_inputs: &[serde_json::Value],
        usage: Option<serde_json::Value>,
    ) {
        if content.is_empty() && tool_call_inputs.is_empty() {
            return;
        }
        let thinking_text = thinking.join("");
        let content_text = content.join("");
        let mut msg = serde_json::json!({
            "role": "assistant",
            "content": content_text,
        });
        if !thinking_text.is_empty() {
            msg["reasoning_content"] = serde_json::Value::String(thinking_text);
        }
        if !tool_call_inputs.is_empty() {
            msg["tool_calls"] = serde_json::Value::Array(tool_call_inputs.to_vec());
        }
        self.add_message(store, msg, usage).await;
    }

    /// Add tool results to the conversation.
    pub async fn add_tool_response(
        &mut self,
        store: &MemoryClient,
        tool_results: &[serde_json::Value],
    ) {
        for result in tool_results {
            self.add_message(store, result.clone(), None).await;
        }
    }

    /// Load an existing session from the database.
    #[allow(dead_code)]
    pub async fn load(store: &MemoryClient, agent_id: &str) -> anyhow::Result<Self> {
        let agent = store
            .get_agent(agent_id)
            .await?
            .ok_or_else(|| anyhow::anyhow!("agent '{agent_id}' not found"))?;
        let messages = store.load_messages(agent_id).await?;
        Ok(Self {
            agent_id: agent.agent_id,
            session_id: agent.session_id,
            agent_idx: agent.agent_idx,
            cwd: agent.cwd,
            messages,
            model_identifier: agent.model_identifier,
            tools: agent.tool_definitions,
            request_params: agent.request_params,
            prompt_id: agent.prompt_id,
            prompt_args: agent.prompt_args,
        })
    }
}

/// The session's CURRENT conversation generation for resume: the highest
/// agent_idx, most recent created_at on ties.
///
/// Compaction starts a new generation (idx+1) whose history is self-contained
/// (system + summary + everything since). Resuming from ANY older generation
/// resurrects superseded history — the model sees stale duplicated context
/// and starts repeating itself — so resume must always pick the chain head.
pub fn pick_resume_agent(agents: &[crow_memory_sdk::AgentRecord]) -> &crow_memory_sdk::AgentRecord {
    agents
        .iter()
        .max_by(|a, b| {
            a.agent_idx
                .cmp(&b.agent_idx)
                .then_with(|| a.created_at.cmp(&b.created_at))
        })
        .expect("list_agents returned empty")
}

/// Create a new agent session with system prompt, persist to DB.
pub async fn make_agent_session(
    config: &Config,
    store: &MemoryClient,
    tools: &serde_json::Value,
    model_id: &str,
    cwd: &str,
    session_id: Option<&str>,
    agent_idx: Option<i64>,
) -> anyhow::Result<AgentSession> {
    // Load template
    let template = if !config.system_prompt.is_empty() {
        config.system_prompt.clone()
    } else {
        let template_path = config.config_dir.join("prompts/system_prompt.hbs");
        std::fs::read_to_string(&template_path).unwrap_or_default()
    };

    let prompt_id = store
        .lookup_or_create_prompt(&template, "crow-default")
        .await?;

    let session_id = session_id
        .map(|s| s.to_string())
        .unwrap_or_else(coolname::generate_slug);
    let agent_idx = agent_idx.unwrap_or(1);
    let agent_id = format!("{session_id}-{agent_idx}");

    // Build template context
    // Agent Skills spec: global skills live in ~/.agents/skills.
    let skills_dir = dirs::home_dir().expect("home dir").join(".agents/skills");
    let skills = get_skills(&skills_dir);
    let display_tree = build_display_tree(cwd);
    let agents_content = build_agents_content(cwd);

    let prompt_args = serde_json::json!({
        "workspace": cwd,
        "display_tree": display_tree,
        "agents_content": agents_content,
        "session_id": session_id,
        "skills": skills,
    });

    // Render system prompt with handlebars
    let system_prompt = render_template(&template, &prompt_args);

    let request_params = serde_json::json!({"temperature": 0.2});

    // Create agent record
    store
        .create_agent(
            &agent_id,
            &session_id,
            agent_idx,
            cwd,
            &prompt_id,
            &prompt_args,
            &system_prompt,
            tools,
            &request_params,
            model_id,
        )
        .await?;

    let mut session = AgentSession {
        agent_id,
        session_id,
        agent_idx,
        cwd: cwd.to_string(),
        messages: Vec::new(),
        model_identifier: model_id.to_string(),
        tools: tools.clone(),
        request_params,
        prompt_id,
        prompt_args,
    };

    // Start with system message
    let sys_msg = serde_json::json!({"role": "system", "content": system_prompt});
    session.add_message(store, sys_msg, None).await;

    Ok(session)
}

/// Render a Handlebars template with context.
fn render_template(template: &str, args: &serde_json::Value) -> String {
    let mut reg = handlebars::Handlebars::new();
    reg.set_strict_mode(false);
    // Register the template inline
    match reg.render_template(template, args) {
        Ok(rendered) => rendered.trim().to_string(),
        Err(e) => {
            tracing::warn!("template render failed: {e}, using raw");
            // Fallback: basic replacement
            template
                .replace("{{ session_id }}", args.get("session_id").and_then(|v| v.as_str()).unwrap_or(""))
                .replace("{{ workspace }}", args.get("workspace").and_then(|v| v.as_str()).unwrap_or(""))
                .replace("{{ display_tree }}", args.get("display_tree").and_then(|v| v.as_str()).unwrap_or(""))
                .replace("{{ agents_content }}", args.get("agents_content").and_then(|v| v.as_str()).unwrap_or(""))
        }
    }
}

/// Scan skills dir, parse SKILL.md frontmatter, return structured skills.
fn get_skills(skills_dir: &Path) -> Vec<serde_json::Value> {
    let mut skills = Vec::new();
    let Ok(entries) = std::fs::read_dir(skills_dir) else {
        return skills;
    };
    let mut dirs: Vec<_> = entries
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .collect();
    dirs.sort_by_key(|d| d.file_name());

    for entry in dirs {
        let skill_md = entry.path().join("SKILL.md");
        let Ok(text) = std::fs::read_to_string(&skill_md) else {
            continue;
        };
        if let Some(meta) = parse_frontmatter(&text) {
            let name = meta.get("name").and_then(|v| v.as_str());
            let description = meta.get("description").and_then(|v| v.as_str());
            if let (Some(name), Some(description)) = (name, description) {
                skills.push(serde_json::json!({
                    "name": name.trim(),
                    "description": description.trim(),
                    "path": skill_md.display().to_string(),
                }));
            }
        }
    }
    skills
}

/// Parse YAML frontmatter between --- markers.
fn parse_frontmatter(text: &str) -> Option<serde_json::Value> {
    if !text.starts_with("---") {
        return None;
    }
    let end = text[3..].find("---")?;
    let yaml_str = &text[3..3 + end];
    let val: serde_yaml::Value = serde_yaml::from_str(yaml_str).ok()?;
    serde_json::to_value(val).ok()
}

/// Build directory tree context block.
fn build_display_tree(cwd: &str) -> String {
    let home = dirs::home_dir().unwrap_or_default();
    let home_str = home.display().to_string();
    let notes_dir = home.join(".crow/notes");
    let skills_dir = home.join(".crow/skills");

    let mut trees = Vec::new();
    let t = directory_tree(&notes_dir);
    if !t.is_empty() {
        trees.push(t);
    }
    let t = directory_tree(&skills_dir);
    if !t.is_empty() {
        trees.push(t);
    }
    // Only add cwd tree if cwd != $HOME
    if std::fs::canonicalize(cwd)
        .map(|p| p != std::fs::canonicalize(&home_str).unwrap_or_default())
        .unwrap_or(true)
    {
        let t = directory_tree(Path::new(cwd));
        if !t.is_empty() {
            trees.push(t);
        }
    }
    trees.join("\n\n")
}

/// Build AGENTS.md context block.
fn build_agents_content(cwd: &str) -> String {
    let home = dirs::home_dir().unwrap_or_default();
    let home_str = home.display().to_string();
    let notes_dir = home.join(".crow/notes");
    let mut parts = Vec::new();

    if let Some(content) = read_agents_file(&notes_dir) {
        parts.push(content);
    }
    if std::fs::canonicalize(cwd)
        .map(|p| p != std::fs::canonicalize(&home_str).unwrap_or_default())
        .unwrap_or(true)
    {
        if let Some(content) = read_agents_file(Path::new(cwd)) {
            parts.push(content);
        }
    }
    if parts.is_empty() {
        "No AGENTS.md found".to_string()
    } else {
        parts.join("\n\n")
    }
}

fn read_agents_file(dir: &Path) -> Option<String> {
    for name in ["AGENTS.typ", "AGENTS.md"] {
        let path = dir.join(name);
        if let Ok(content) = std::fs::read_to_string(&path) {
            return Some(content);
        }
    }
    None
}

/// Generate a directory tree string (max depth 3, ignoring common noise).
fn directory_tree(root: &Path) -> String {
    let ignores = [
        "node_modules",
        "__pycache__",
        ".venv",
        "refs",
        "target",
        ".git",
    ];
    let mut lines = Vec::new();
    let root_name = root
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| root.display().to_string());
    lines.push(format!("{root_name}/"));
    walk_tree(root, "", 0, 3, &ignores, &mut lines);
    if lines.len() <= 1 {
        return String::new();
    }
    lines.join("\n")
}

fn walk_tree(
    dir: &Path,
    prefix: &str,
    depth: usize,
    max_depth: usize,
    ignores: &[&str],
    lines: &mut Vec<String>,
) {
    if depth >= max_depth {
        return;
    }
    let mut entries: Vec<_> = match std::fs::read_dir(dir) {
        Ok(e) => e.filter_map(|e| e.ok()).collect(),
        Err(_) => return,
    };
    entries.sort_by_key(|e| {
        let is_dir = e.file_type().map(|t| t.is_dir()).unwrap_or(false);
        (std::cmp::Reverse(is_dir), e.file_name())
    });

    // Filter ignores and hidden files (except .crow)
    entries.retain(|e| {
        let name = e.file_name().to_string_lossy().to_string();
        if ignores.contains(&name.as_str()) {
            return false;
        }
        if name.starts_with('.') && name != ".crow" {
            return false;
        }
        // Skip egg_info patterns
        if name.ends_with(".egg-info") {
            return false;
        }
        true
    });

    for (i, entry) in entries.iter().enumerate() {
        let is_last = i == entries.len() - 1;
        let connector = if is_last { "└── " } else { "├── " };
        let name = entry.file_name().to_string_lossy().to_string();
        let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);

        if is_dir {
            lines.push(format!("{prefix}{connector}{name}/"));
            let new_prefix = format!("{prefix}{}", if is_last { "    " } else { "│   " });
            walk_tree(&entry.path(), &new_prefix, depth + 1, max_depth, ignores, lines);
        } else {
            lines.push(format!("{prefix}{connector}{name}"));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crow_memory_sdk::AgentRecord;

    fn rec(agent_id: &str, idx: i64, created_at: &str) -> AgentRecord {
        AgentRecord {
            agent_id: agent_id.to_string(),
            session_id: "s".to_string(),
            agent_idx: idx,
            cwd: "/tmp".to_string(),
            prompt_id: String::new(),
            prompt_args: serde_json::Value::Null,
            system_prompt: String::new(),
            tool_definitions: serde_json::Value::Null,
            request_params: serde_json::Value::Null,
            model_identifier: "m".to_string(),
            status: "active".to_string(),
            created_at: created_at.to_string(),
        }
    }

    #[test]
    fn resume_picks_highest_idx() {
        let agents = vec![
            rec("s-1", 1, "2026-08-04T12:52:04.000000000+00:00"),
            rec("s-2", 2, "2026-08-04T13:43:24.000000000+00:00"),
        ];
        assert_eq!(pick_resume_agent(&agents).agent_id, "s-2");
    }

    #[test]
    fn system_prompt_template_renders_skills() {
        let template = include_str!("../assets/system_prompt.hbs");
        let args = serde_json::json!({
            "session_id": "cool-name",
            "workspace": "/tmp/ws",
            "display_tree": "tree-here",
            "agents_content": "agents-here",
            "skills": [
                {"name": "plan-todo", "description": "Plan with todos", "path": "/x/plan-todo/SKILL.md"},
            ],
        });
        let rendered = render_template(template, &args);
        assert!(rendered.contains("session id cool-name"));
        assert!(rendered.contains("<SKILLS>"));
        assert!(rendered.contains("**plan-todo** — Plan with todos"));
        assert!(rendered.contains("`/x/plan-todo/SKILL.md`"));
        // No leftover template syntax
        assert!(!rendered.contains("{%"));
        assert!(!rendered.contains("{{"));
        // Content must not be HTML-escaped (triple-mustache used for prose)
        assert!(!rendered.contains("&#x60;"));
    }

    #[test]
    fn system_prompt_template_omits_skills_when_empty() {
        let template = include_str!("../assets/system_prompt.hbs");
        let args = serde_json::json!({
            "session_id": "s",
            "workspace": "/tmp",
            "display_tree": "",
            "agents_content": "",
            "skills": [],
        });
        let rendered = render_template(template, &args);
        // The skills block itself is omitted (the MEMORY section only mentions it in prose)
        assert!(!rendered.contains("You have skills available"));
    }

    #[test]
    fn resume_picks_latest_created_on_idx_tie() {
        // Duplicate generation rows (historical bug: resurrected old runs
        // re-compacted into the same idx) — the newest row is the chain head.
        let agents = vec![
            rec("s-1", 1, "2026-08-04T12:52:04.000000000+00:00"),
            rec("s-2", 2, "2026-08-04T13:43:24.000000000+00:00"),
            rec("s-2", 2, "2026-08-04T14:51:18.000000000+00:00"),
            rec("s-2", 2, "2026-08-04T14:23:51.000000000+00:00"),
        ];
        let picked = pick_resume_agent(&agents);
        assert_eq!(picked.agent_idx, 2);
        assert_eq!(picked.created_at, "2026-08-04T14:51:18.000000000+00:00");
    }

    #[test]
    fn resume_single_record() {
        let agents = vec![rec("s-1", 1, "2026-08-04T12:52:04.000000000+00:00")];
        assert_eq!(pick_resume_agent(&agents).agent_id, "s-1");
    }
}

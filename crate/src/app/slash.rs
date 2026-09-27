//! slash: App methods for the slash surface (Phase 2 split).

use super::*;
use crate::bus::Cmd;
use crate::controller::Controller;
use crate::locale::Locale;
use crate::transcript::NoticeLevel;

impl App {
    pub(crate) fn slash_completion_open(&self) -> bool {
        !self.slash_completion_dismissed && !self.slash_matches().is_empty()
    }


    pub fn slash_matches(&self) -> Vec<SlashEntry> {
        let first = &self.input.lines()[0];
        if !first.starts_with('/') {
            return Vec::new();
        }
        if let Some((name, arg)) = first[1..].split_once(' ') {
            return self.slash_argument_matches(name, arg);
        }
        let prefix = &first[1..];
        let mut out: Vec<SlashEntry> = SLASH_COMMANDS
            .iter()
            .filter(|c| c.name.starts_with(prefix))
            .map(|c| SlashEntry {
                disabled: false,
                name: c.name.to_string(),
                usage: c.usage.to_string(),
                desc: self.locale.command_desc(c.name, c.desc).to_string(),
                skill: false,
                plugin: false,
                section: None,
                completion: None,
            })
            .collect();
        let mut plugins: Vec<_> = self
            .plugin_commands
            .iter()
            .filter(|command| {
                command.name.starts_with(prefix)
                    && !SLASH_COMMANDS.iter().any(|c| c.name == command.name)
            })
            .collect();
        plugins.sort_by(|a, b| a.name.cmp(&b.name));
        for command in plugins {
            out.push(SlashEntry {
                disabled: false,
                name: command.name.clone(),
                usage: command
                    .input
                    .as_ref()
                    .map(|input| format!("/{} [{}]", command.name, input.hint))
                    .unwrap_or_else(|| format!("/{}", command.name)),
                desc: self
                    .locale
                    .plugin_command_desc(&command.name, &command.description)
                    .to_string(),
                skill: false,
                plugin: true,
                section: None,
                completion: None,
            });
        }
        // Host skills share the '/' namespace. Builtins win first, then an
        // active client command, because the latter never enters a prompt.
        // Each group stays alphabetical so the menu reads in name order.
        let mut skills: Vec<_> = self
            .skills
            .iter()
            .filter(|s| {
                !s.name.eq_ignore_ascii_case("logout")
                    && s.name.starts_with(prefix)
                    && !SLASH_COMMANDS.iter().any(|c| c.name == s.name)
                    && !self.plugin_command_active(&s.name)
            })
            .collect();
        skills.sort_by(|a, b| a.name.cmp(&b.name));
        for s in skills {
            out.push(SlashEntry {
                disabled: false,
                name: s.name.clone(),
                usage: s
                    .input_hint
                    .as_ref()
                    .map(|hint| format!("/{} {}", s.name, hint))
                    .unwrap_or_else(|| format!("/{}", s.name)),
                desc: s.description.clone(),
                skill: !s.client_command,
                plugin: s.client_command,
                section: None,
                completion: None,
            });
        }
        // An exact command must win over a longer name sharing its prefix.
        out.sort_by_key(|entry| entry.name != prefix);
        out
    }

    pub(crate) fn slash_argument_matches(&self, name: &str, arg: &str) -> Vec<SlashEntry> {
        let prefix = arg.trim_start();
        if prefix.contains(char::is_whitespace) {
            return Vec::new();
        }

        if !SLASH_COMMANDS.iter().any(|command| command.name == name) {
            if let Some(command) = self
                .plugin_commands
                .iter()
                .find(|command| command.name == name)
            {
                return command
                    .input
                    .as_ref()
                    .into_iter()
                    .flat_map(|input| input.options.iter())
                    .filter(|option| option.value.starts_with(prefix))
                    .map(|option| SlashEntry {
                        disabled: option.disabled,
                        name: name.to_string(),
                        usage: option.label.clone().unwrap_or_else(|| option.value.clone()),
                        desc: option.description.clone().unwrap_or_default(),
                        skill: false,
                        plugin: true,
                        section: None,
                        completion: Some(format!("/{name} {}", option.value)),
                    })
                    .collect();
            }
        }

        self.builtin_argument_options(name)
            .into_iter()
            .filter(|(value, _, _)| value.starts_with(prefix))
            .map(|(value, label, desc)| SlashEntry {
                disabled: false,
                section: match (name, value.as_str()) {
                    ("theme", "toggle") => {
                        Some(self.locale.tr("Appearance", "明暗模式").to_string())
                    }
                    ("theme", _) => Some(self.locale.tr("Themes", "主题包").to_string()),
                    _ => None,
                },
                name: name.to_string(),
                usage: label,
                desc,
                skill: false,
                plugin: false,
                completion: Some(format!("/{name} {value}")),
            })
            .collect()
    }

    /// The value currently in effect for an open builtin option menu
    /// (`/model `, `/effort `, `/agent `, `/theme `, `/permission `), if
    /// the menu is one. Command-name lists and plugin option lists carry no
    /// client-side "current". Mirrors the pickers (issue #102).
    pub(crate) fn builtin_option_current(&self, matches: &[SlashEntry]) -> Option<String> {
        let first = matches.first()?;
        if first.completion.is_none() || matches.iter().any(|entry| entry.plugin) {
            return None;
        }
        match first.name.as_str() {
            "model" => Some(self.current_model()),
            "effort" => self.modes.effort.clone(),
            "agent" => Some(self.current_mode()),
            "harness" => crate::harness::current_id(&self.harness_settings_path()),
            "theme" => Some(self.active_palette_id.clone()),
            "permission" => Some(self.current_permission().to_string()),
            _ => None,
        }
    }

    /// Restart the slash menu selection on the option currently in effect
    /// when the open menu is a builtin option list; other menus restart at
    /// their head. Text edits call this instead of pinning `slash_sel` to 0
    /// so `/model ` / `/effort ` open on the running value (issue #102).
    pub(crate) fn snap_slash_sel(&mut self) {
        let matches = self.slash_matches();
        let current = self.builtin_option_current(&matches);
        self.slash_sel = current
            .and_then(|value| {
                matches.iter().position(|entry| {
                    entry.completion.as_deref().and_then(|completion| {
                        completion.strip_prefix(&format!("/{} ", entry.name))
                    }) == Some(value.as_str())
                })
            })
            .unwrap_or(0);
    }

    pub(crate) fn builtin_argument_options(&self, name: &str) -> Vec<(String, String, String)> {
        let plain =
            |value: &str, desc: &str| (value.to_string(), value.to_string(), desc.to_string());
        match name {
            "model" => {
                // The option list always carries the effective model (pick →
                // stream → config default) so the inline menu can mark and
                // preselect what the session runs (issue #102).
                let current = self.current_model();
                if !self.last_models.is_empty() {
                    let mut rows: Vec<(String, String, String)> = self
                        .last_models
                        .iter()
                        .map(|model| {
                            (
                                model.id.clone(),
                                model.name.clone(),
                                model.provider.clone(),
                            )
                        })
                        .collect();
                    if !rows.iter().any(|(id, _, _)| id == &current) {
                        rows.insert(0, (current.clone(), current.clone(), String::new()));
                    }
                    return rows;
                }
                let mut ids = MODEL_PRESETS
                    .iter()
                    .map(|value| (*value).to_string())
                    .collect::<Vec<_>>();
                if !ids.iter().any(|id| id == &current) {
                    ids.insert(0, current);
                }
                ids.into_iter()
                    .map(|id| (id.clone(), id, String::new()))
                    .collect()
            }
            "agent" if !self.last_presets.is_empty() => self
                .last_presets
                .iter()
                .map(|preset| {
                    (
                        preset.id.clone(),
                        preset.name.clone(),
                        preset.description.clone(),
                    )
                })
                .collect(),
            "agent" => AGENT_MODES
                .iter()
                .map(|(id, label, desc)| {
                    ((*id).to_string(), (*label).to_string(), (*desc).to_string())
                })
                .collect(),
            "harness" => crate::harness::all(&self.harness_settings_path())
                .into_iter()
                .map(|entry| {
                    let command = entry.command_text();
                    (entry.id, entry.label, command)
                })
                .collect(),
            "effort" if !self.effort_choices.is_empty() => self
                .effort_choices
                .iter()
                .map(|effort| (effort.clone(), effort.clone(), String::new()))
                .collect(),
            "effort" => vec![
                plain("off", "disable extended reasoning"),
                plain("high", "high reasoning effort"),
                plain("max", "maximum reasoning effort"),
            ],
            "permission" if !self.permission_choices.is_empty() => self
                .permission_choices
                .iter()
                .map(|preset| {
                    (
                        preset.id.clone(),
                        preset.name.clone(),
                        preset.description.clone(),
                    )
                })
                .collect(),
            "permission" => PERMISSION_PRESETS
                .iter()
                .map(|(id, desc)| plain(id, desc))
                .collect(),
            "plan" => vec![
                plain("on", "enable plan mode"),
                plain("off", "disable plan mode"),
            ],
            "theme" => {
                let mut options = vec![(
                    "toggle".to_string(),
                    self.locale
                        .tr("Toggle dark / light", "切换 dark / light")
                        .to_string(),
                    self.locale
                        .tr("switch the current theme mode", "切换当前主题的明暗模式")
                        .to_string(),
                )];
                options.extend(self.palettes.iter().map(|palette| {
                    let builtin = crate::theme::BUILTIN_PALETTE_IDS
                        .contains(&palette.id.as_str());
                    (
                        palette.id.clone(),
                        palette.label.clone(),
                        match (builtin, palette.loaded) {
                            (_, false) => "theme plugin · stopped".to_string(),
                            (true, _) => "builtin".to_string(),
                            (false, _) => "theme plugin".to_string(),
                        },
                    )
                }));
                options
            }
            "ui" => self
                .ui_plugins
                .iter()
                .map(|plugin| {
                    (
                        plugin.id.clone(),
                        plugin.label.clone(),
                        format!("{} · {}", plugin.source, plugin.status),
                    )
                })
                .collect(),
            "auth" => self
                .auth
                .methods
                .iter()
                .map(|method| {
                    (
                        method.id.clone(),
                        method.name.clone().unwrap_or_else(|| method.id.clone()),
                        method.description.clone().unwrap_or_default(),
                    )
                })
                .collect(),
            "lang" => vec![plain("zh", "中文"), plain("en", "English")],
            "liang" => vec![plain("on", "show pet"), plain("off", "hide pet")],
            "session" => vec![
                plain("view", "show session + runtime info"),
                plain("prev", "switch to the previous session tab"),
                plain("next", "switch to the next session tab"),
            ],
            _ => Vec::new(),
        }
    }


    pub(crate) fn history_prev(&mut self) {
        self.input_sel = None;
        if !self.input.is_empty() && self.input.hist_pos.is_none() {
            return; // grok: history opens from an empty prompt
        }
        if self.input.history.is_empty() {
            return;
        }
        let pos = match self.input.hist_pos {
            None => {
                self.input.stash = self.input.buf();
                self.input.history.len() - 1
            }
            Some(0) => 0,
            Some(p) => p - 1,
        };
        self.input.hist_pos = Some(pos);
        self.input.set(self.input.history[pos].clone());
    }

    pub(crate) fn history_prev_from_draft(&mut self) {
        self.input_sel = None;
        if self.input.history.is_empty() {
            return;
        }
        if self.input.hist_pos.is_none() {
            self.input.stash = self.input.buf();
        }
        let pos = match self.input.hist_pos {
            None => self.input.history.len() - 1,
            Some(0) => 0,
            Some(p) => p - 1,
        };
        self.input.hist_pos = Some(pos);
        self.input.set(self.input.history[pos].clone());
    }

    pub(crate) fn history_next(&mut self) {
        self.input_sel = None;
        let Some(pos) = self.input.hist_pos else {
            return;
        };
        if pos + 1 >= self.input.history.len() {
            self.input.hist_pos = None;
            let stash = std::mem::take(&mut self.input.stash);
            self.input.set(stash);
        } else {
            self.input.hist_pos = Some(pos + 1);
            self.input.set(self.input.history[pos + 1].clone());
        }
    }

    pub(crate) fn accept_slash(&mut self, entry: &SlashEntry, ctl: &Controller) {
        if entry.disabled { return; }
        if let Some(completion) = &entry.completion {
            self.input.set(completion.clone());
        }
        if entry.plugin {
            let line = self.input.buf();
            let rest = line
                .strip_prefix('/')
                .and_then(|s| s.strip_prefix(entry.name.as_str()))
                .unwrap_or("")
                .trim()
                .to_string();
            self.input.history.push(line);
            self.input.clear();
            self.slash_sel = 0;
            ctl.send(Cmd::InvokePluginCommand {
                name: entry.name.clone(),
                args: rest,
            });
            return;
        }
        if entry.skill {
            // Web-UI semantics: picking a skill lands the literal "/name "
            // in the composer; enter on the completed line ships it as an
            // ordinary prompt and the host injects the skill body.
            let full = format!("/{}", entry.name);
            let line = self.input.buf().trim().to_string();
            if line == full || line.starts_with(&format!("{full} ")) {
                self.submit(ctl);
            } else {
                self.input.set(format!("{full} "));
                self.slash_sel = 0;
            }
            return;
        }
        let line = self.input.buf();
        let rest = line
            .strip_prefix('/')
            .and_then(|s| s.strip_prefix(entry.name.as_str()))
            .unwrap_or("")
            .trim()
            .to_string();
        self.input.clear();
        self.slash_sel = 0;
        self.run_slash(&entry.name, &rest, ctl);
    }

    pub fn run_slash(&mut self, name: &str, arg: &str, ctl: &Controller) {
        match name {
            "help" => self.push_help(),
            "keys" => self.push_keys(),
            "lang" => self.set_locale(arg),
            "clear" => {
                self.transcript.clear();
                self.sel = None;
                self.transcript.push_notice(
                    NoticeLevel::Info,
                    self.locale.tr("scrollback cleared", "滚动区已清空").into(),
                );
            }
            "quit" => self.quit = true,
            "liang" => {
                self.pet_visible = match arg {
                    "on" | "show" => true,
                    "off" | "hide" => false,
                    _ => !self.pet_visible,
                };
                let msg = if self.pet_visible {
                    "🤫 小难梁已召唤 — 安静，他在想 AGI · /liang 收回"
                } else {
                    "小难梁去隆基市场买卡了 — /liang 再次召唤"
                };
                self.show_tip(msg);
            }
            "harness" => {
                if arg.is_empty() {
                    self.open_harness_picker();
                } else {
                    self.switch_harness(arg, ctl);
                }
            }
            "theme" => self.apply_theme_arg(arg, ctl),
            "vim" => {
                let on = match arg {
                    "on" | "1" => true,
                    "off" | "0" => false,
                    _ => !self.vim.is_active(),
                };
                self.vim.set(on);
                self.show_tip(self.locale.tr(
                    "vim mode — i insert · esc normal · /vim off",
                    "vim 模式 — i 插入 · esc 返回 normal · /vim off 关闭",
                ));
            }
            "ui" => {
                if arg.is_empty() {
                    self.open_ui_plugin_picker();
                } else if self.ui_plugins.iter().any(|plugin| plugin.id == arg) {
                    ctl.send(Cmd::PluginUiSelected {
                        agent_id: self.session_id.clone(),
                        id: arg.to_string(),
                    });
                } else {
                    self.show_tip(self.locale.trf(
                    "unknown UI Plugin: {}",
                    "未知 UI 插件：{}",
                    &[arg.into()],
                ));
                }
            }
            "plugins" => {
                ctl.send(Cmd::FetchStaticPlugins);
                self.show_tip(self.locale.tr(
                    "reading static plugins from Host…",
                    "正在从 Host 读取静态插件…",
                ));
            }
            "cordis-plugins" => {
                ctl.send(Cmd::FetchCordisPlugins {
                    agent_id: self.session_id.clone(),
                });
                self.show_tip(self.locale.tr(
                    "reading dynamic Cordis plugins from Host…",
                    "正在从 Host 读取动态 Cordis 插件…",
                ));
            }
            "model" => {
                if arg.is_empty() {
                    self.open_model_picker(ctl);
                } else {
                    self.set_model(arg.to_string(), ctl);
                }
            }
            "agent" => {
                if arg.is_empty() {
                    self.open_mode_picker(ctl);
                } else {
                    self.set_mode(arg.to_string(), ctl);
                }
            }
            "new" => self.new_session_flow(arg, ctl),
            "close" => self.close_session_flow(ctl),
            "session" => match arg {
                "view" | "" => self.push_session_info(),
                "prev" => {
                    let count = self.session_tab_count();
                    if count > 1 {
                        let prev =
                            if self.current == 0 { count - 1 } else { self.current - 1 };
                        self.switch_view_to_tab(prev, ctl);
                    }
                }
                "next" => {
                    let count = self.session_tab_count();
                    if count > 1 {
                        let next = (self.current + 1) % count;
                        self.switch_view_to_tab(next, ctl);
                    }
                }
                _ => self.show_tip(self.locale.tr(
                    "usage: /session [view|prev|next]",
                    "用法：/session [view|prev|next]",
                )),
            },
            "status" => self.push_status_info(),
            "auth" => self.start_auth(arg, ctl),
            "resume" => {
                // `/resume [n|id]` — a bare number is how many of the most
                // recent durable sessions to list (default 50); anything
                // else is an id prefix to resume.
                if arg.is_empty() {
                    self.open_resume_picker(crate::sessions::DEFAULT_SESSION_LIST_LIMIT, ctl);
                } else if let Ok(n) = arg.parse::<usize>() {
                    self.open_resume_picker(n.max(1), ctl);
                } else if !self.demo && self.list_session {
                    ctl.send(Cmd::ListSessions {
                        requester_session_id: self.session_id.clone(),
                        prefix: Some(arg.to_string()),
                        limit: usize::MAX,
                    });
                    self.show_tip(self.locale.tr("listing ACP sessions…", "正在列出 ACP 会话…"));
                } else if !self.demo && (self.resume_session_cap || self.load_session) {
                    self.resume_acp_session(arg, ctl);
                } else {
                    if !self.demo {
                        self.show_tip(self.locale.tr(
                            "agent did not advertise session/resume or loadSession — replaying local JSONL",
                            "Agent 未声明 session/resume 或 loadSession —— 改为回放本地 JSONL",
                        ));
                    }
                    self.resume_session(arg, ctl);
                }
            }
            "effort" => {
                if arg.is_empty() {
                    ctl.send(Cmd::FetchEfforts {
                        session_id: self.session_id.clone(),
                        provider: self.cfg.provider.clone(),
                        model: self.cfg.model.clone(),
                    });
                } else {
                    ctl.send(Cmd::SelectModel {
                        session_id: self.session_id.clone(),
                        provider: None,
                        model: None,
                        effort: Some(arg.to_string()),
                    });
                    self.modes.effort = Some(arg.to_string());
                }
            }
            "permission" => {
                if arg.is_empty() {
                    self.open_permission_picker();
                } else if let Some(preset) = normalize_permission(arg) {
                    self.set_permission(preset.to_string(), ctl);
                } else {
                    // Not a stock spelling — pass through for custom preset
                    // tables; the host lists what it knows on a miss.
                    self.set_permission(arg.to_string(), ctl);
                }
            }
            "plan" => {
                if let Some(action) = self
                    .skills
                    .iter()
                    .find(|command| command.name == "plan")
                    .and_then(|command| command.config_action.clone())
                {
                    let value = match arg {
                        "" if self.modes.plan => action.reset_value.clone(),
                        "" | "on" => Some(action.value.clone()),
                        "off" => action.reset_value.clone(),
                        _ => None,
                    };
                    if let Some(value) = value {
                        ctl.send(Cmd::SetConfigOption {
                            session_id: self.session_id.clone(),
                            config_id: action.config_id,
                            value,
                        });
                        return;
                    }
                }
                // Agents without a declared config action keep the ordinary
                // ACP slash-prompt transport; `/plan message` also belongs to
                // the command handler rather than the config switch.
                let text = if arg.is_empty() {
                    "/plan".to_string()
                } else {
                    format!("/plan {arg}")
                };
                self.send_agent_text(text, ctl);
            }
            "image" => self.send_image(arg, ctl),
            "clip" => self.clip_image(arg, ctl),
            other => {
                self.transcript.push_notice(
                    NoticeLevel::Warn,
                    if self.locale == Locale::Zh {
                        format!("未知命令 /{other} — 使用 /help 查看命令")
                    } else {
                        format!("unknown command /{other} — /help lists commands")
                    },
                );
            }
        }
    }
}

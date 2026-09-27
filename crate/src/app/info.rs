//! info: App methods for the info surface (Phase 2 split).

use super::*;
use crate::locale::Locale;

impl App {
    pub(crate) fn push_help(&mut self) {
        if self.locale == Locale::Zh {
            let text = "\
- enter · 发送；空 composer 且 Queue 非空时立即发送队首
- alt+↑ · 选择任意排队消息；↑/↓ 选择，enter 编辑/保存，ctrl+d 删除，esc 退出
- ctrl+enter · 立即 steer 当前轮次
- esc · 优先退出 / 推荐；队列编辑时取消；否则中断（保留草稿），空闲时清草稿
- ctrl+c · 有草稿先清除；无草稿时连按 2 次退出（不中断）
- shift+tab · 轮换权限预设 · /permission 打开选择器
- ctrl+p · 打开模型选择器，然后选择推理强度
- ctrl+shift+a · 直接轮换 Agent 预设
- ↓ · 空输入时展开 Agent 会话导航；←/→ 选择，enter 打开，esc 折叠
- /agent · 切换 ACP 广告的 Agent 预设
- /lang · 切换界面语言：/lang zh 或 /lang en
- /auth · ACP 登录；多种方式时打开选择器
- /effort · 推理强度 · /permission 权限预设 · /plan 计划模式
- /resume · 恢复持久会话并继续写入原日志
- /image · 暂存本地图片：/image ./pic.png [说明]
- /clip · 暂存剪贴板图片；ctrl+v 同样可用
- !cmd · 在会话级本地 shell 中运行命令，不经过 Agent；初始目录为 workspace，cd/环境变量跨命令保留
- /<skill> · Agent 命令会进入 / 菜单，选择后由 Host 注入技能正文
- ctrl+o · 展开思考和工具输出 · ctrl+l · 清屏
- 输入框编辑：readline 组合键 + ⌘/⌥ 方向键 + 键盘选区 · 完整映射见 /keys
- 点击工具 · 展开/折叠 · 滚轮滚动对话
- pgup/pgdn · 翻页 · end 回到最新消息
- 鼠标拖动 · 选择并复制文本 · 双击复制单词

每轮会显示：流式思考与回答、工具调用与结果、注入上下文、Subagent 生命周期、
token 用量（含缓存命中）以及轮次结束原因。";
            self.open_text_overlay("builtin.help", self.locale.tr("help", "帮助").to_string(), text.to_string());
            return;
        }
        let text = "\
- enter · send · with an empty composer, sends the Queue head now
- alt+↑ · choose any queued prompt · ↑/↓ select, enter edits/saves, ctrl+d deletes, esc closes
- ctrl+enter · steer the active turn immediately
- esc · first closes / suggestions; cancels queue edits; otherwise interrupts (draft survives) or clears an idle draft
- ctrl+c · clear a draft; 2× quits with no draft (never interrupts)
- shift+tab · cycle permission (workspace-write ⇄ full access) · /permission opens the preset picker
- ctrl+p · model picker (host catalog) → effort picker
- ctrl+shift+a · cycle agent preset directly
- ↓ · expand Agent transcript navigation from an empty prompt · ←/→ choose, enter opens, esc collapses
- /agent · switch the agent preset advertised over ACP
- /auth · ACP sign-in (picker when several methods; else Terminal Auth or authenticate _meta)
- /effort · reasoning effort · /permission preset · /plan host plan mode
- /resume · pick up a durable session — transcript replays, log continues
- /image · stage a local image — /image ./pic.png [caption]
- /clip · stage the clipboard image — /clip [caption] · ctrl+v also works
- !cmd · run in the session's local shell (not the agent); starts in the workspace, keeps cd/env across commands
- /<skill> · agent commands join the / menu — enter ships it and the host injects the skill body
- ctrl+o · expand thoughts + tool output · ctrl+l · clear
- editing · readline chords + ⌘/⌥ arrows (ctrl+arrows elsewhere) · full map in /keys
- click tool · expand/collapse that tool · wheel scrolls the conversation
- pgup/pgdn · scroll · mouse wheel works · end follows the tail
- mouse drag · select text — copied on release · 2×click copies a word

Per turn: streamed reasoning, answer, tool calls with results, injected
context, subagent lifecycles, token usage (incl. cache hits), end reason.";
        self.open_text_overlay("builtin.help", self.locale.tr("help", "帮助").to_string(), text.to_string());
    }

    pub(crate) fn push_keys(&mut self) {
        let text = crate::input::keymap::keys_markdown(
            self.locale == Locale::Zh,
            cfg!(target_os = "macos"),
        );
        self.view_overlay = Some(ViewOverlay {
            id: "builtin.keys".into(),
            title: self.locale.tr("Keyboard shortcuts", "快捷键").to_string(),
            nodes: vec![crate::slots::TuiNode::Markdown {
                id: "keys".into(),
                text,
                streaming: false,
            }],
            scroll: 0,
            notify_plugin: false,
        });
    }

    pub(crate) fn push_session_info(&mut self) {
        let creds = if self.demo {
            "demo mode (no API calls)".to_string()
        } else if self.auth.status == crate::acp_auth::AuthStatus::Configured {
            match self
                .auth
                .method_name
                .as_deref()
                .or(self.auth.method_id.as_deref())
            {
                Some(name) => format!("ACP authenticate · {name}"),
                None => "ready · credential source not reported".into(),
            }
        } else if self.auth.status == crate::acp_auth::AuthStatus::SigningIn {
            "signing in — waiting for Agent response".into()
        } else if self.auth.status == crate::acp_auth::AuthStatus::Failed {
            format!("sign-in failed · {} · /auth", self.auth.message.as_deref().unwrap_or("ACP authenticate failed"))
        } else if self.auth.status == crate::acp_auth::AuthStatus::NeedsAuth {
            match self
                .auth
                .method_name
                .as_deref()
                .or(self.auth.method_id.as_deref())
            {
                Some(name) => format!("sign-in needed · {name} · /auth"),
                None => "sign-in needed · /auth".into(),
            }
        } else if self.cfg.has_credentials() {
            match self.cfg.credential_source() {
                Some(src) => format!("api key present · {src}"),
                None => "api key present".to_string(),
            }
        } else {
            "DEEPSEEK_API_KEY not set".to_string()
        };
        let u = self.transcript.usage;
        let total = u.input + u.output + u.cached + u.reasoning;
        let s = self.transcript.stats;
        let llm_millis = s.turn_millis.saturating_sub(s.tool_millis);
        // The same facts the Client-side `acpSessionStats` service folds —
        // rendered here from the transcript's own accumulator.
        let effort_line = self
            .modes
            .effort
            .as_deref()
            .map(|effort| format!("\n- effort · {effort}"))
            .unwrap_or_default();
        // Context meter from the agent's `usage_update`, when it sends one.
        let context_line = self
            .transcript
            .context
            .map(|ctx| {
                format!(
                    "\n- context · {} of {} ({}%)",
                    fmt_tokens(ctx.used),
                    fmt_tokens(ctx.size),
                    (ctx.fraction() * 100.0).round() as u64
                )
            })
            .unwrap_or_default();
        let mut text = format!(
            "- session · {}{}\n\
             - provider · {} / {}{}\n\
             - agent · {}{}\n\
             - workspace · {}\n\
             - session root · {}\n\
             - runtime · {}\n\
             - server · {}\n\
             - credentials · {}\n\
             - tokens · ↑{} ↓{} (cached {} · reasoning {}) · Σ {}{}\n\
             - turns · {} · steps · {}\n\
             - LLM · {} · tool · {}",
            self.session_id,
            self.session_title
                .as_deref()
                .map(|t| format!(" · {t}"))
                .unwrap_or_default(),
            self.cfg.provider,
            self.cfg.model,
            effort_line,
            self.agent_label(&self.current_mode()),
            if self.modes.agent_preset.is_none() {
                " (default)"
            } else {
                ""
            },
            self.cfg.workspace,
            self.cfg.session_root,
            self.cfg.bin,
            self.server_info.as_deref().unwrap_or("not started"),
            creds,
            fmt_tokens(u.input),
            fmt_tokens(u.output),
            fmt_tokens(u.cached),
            fmt_tokens(u.reasoning),
            fmt_tokens(total),
            context_line,
            s.turns,
            s.steps,
            fmt_duration(llm_millis),
            fmt_duration(s.tool_millis),
        );
        if s.ttft_count > 0 {
            text.push_str(&format!(
                "\n- TTFT avg · {}",
                fmt_duration(s.ttft_total_millis / s.ttft_count as u64)
            ));
        }
        if llm_millis > 0 && u.output > 0 {
            text.push_str(&format!(
                "\n- rate · {:.1} tok/s",
                u.output as f64 / (llm_millis as f64 / 1000.0)
            ));
        }
        self.open_text_overlay(
            "builtin.session",
            self.locale.tr("session", "会话").to_string(),
            text,
        );
    }

    /// Open one builtin info dialog (popup) from a markdown body. `/keys`,
    /// `/help`, `/session` and the painter-side `/status` fallback share this
    /// surface, so the facts never land in the scrollback as transcript cells.
    pub(crate) fn open_text_overlay(&mut self, id: &str, title: String, text: String) {
        self.view_overlay = Some(ViewOverlay {
            id: id.into(),
            title,
            nodes: vec![crate::slots::TuiNode::Markdown {
                id: id.into(),
                text,
                streaming: false,
            }],
            scroll: 0,
            notify_plugin: false,
        });
    }

    /// Compact status fallback: the run state plus painter-owned ACP facts.
    ///
    /// The live `/status` is a Client Plugin command (`status-view`): it opens
    /// the semantic overlay and takes every token/turn/step/timing figure from
    /// the Client-side `acpSessionStats.current()` — the same snapshot
    /// `stats-view` renders in the composer dock. This arm only serves runs
    /// without a Client tree (demo, standalone painter) and deliberately
    /// reads no `Transcript.usage`/`stats` accumulator, so the two surfaces
    /// can never drift apart.
    pub(crate) fn push_status_info(&mut self) {
        let state = match self.state {
            RunState::Idle => self.locale.tr("idle", "空闲").to_string(),
            RunState::Starting => self.locale.tr("starting", "启动中").to_string(),
            RunState::Running => self.locale.tr("running", "工作中").to_string(),
        };
        let perm = self
            .modes
            .permission
            .clone()
            .or_else(|| self.modes.sandbox.clone())
            .unwrap_or_else(|| self.current_permission().to_string());
        let perm_label = if self.locale == Locale::Zh {
            match perm.as_str() {
                "read-only" => "只读".to_string(),
                "workspace-write" => "工作区可写".to_string(),
                "danger-full-access" => "完全访问".to_string(),
                _ => permission_label(&perm),
            }
        } else {
            permission_label(&perm)
        };
        let effort_line = self
            .modes
            .effort
            .as_deref()
            .map(|effort| format!("\n- effort · {effort}"))
            .unwrap_or_default();
        // ACP facts: connection, authenticate state, session binding, and
        // the server banner when the runtime has reported it.
        let acp = if self.demo {
            "demo".to_string()
        } else if self.connection_error.is_some() {
            "failed".to_string()
        } else if self.attached {
            "attached".to_string()
        } else {
            "not attached".to_string()
        };
        let auth_line = match self.auth.status {
            crate::acp_auth::AuthStatus::SigningIn => Some("signing in — waiting for Agent response".into()),
            crate::acp_auth::AuthStatus::Failed => Some(format!("sign-in failed · {}", self.auth.message.as_deref().unwrap_or("ACP authenticate failed"))),
            crate::acp_auth::AuthStatus::Configured => {
                let method = self
                    .auth
                    .method_name
                    .as_deref()
                    .or(self.auth.method_id.as_deref());
                Some(format!(
                    "configured{}",
                    method.map(|m| format!(" · {m}")).unwrap_or_default()
                ))
            }
            crate::acp_auth::AuthStatus::NeedsAuth => {
                let method = self
                    .auth
                    .method_name
                    .as_deref()
                    .or(self.auth.method_id.as_deref());
                Some(format!(
                    "needs sign-in{}",
                    method.map(|m| format!(" · {m}")).unwrap_or_default()
                ))
            }
            _ => None,
        };
        // The negotiated stack, when there is one: `acp` or `acp2`. This is the
        // only place the full fact is spelled out — the meta row carries it as a
        // badge next to the agent name, and the demo/legacy paths never
        // negotiate so they have no line at all.
        let protocol_line = self
            .protocol_tag
            .map(|tag| format!("\n- protocol · {tag}"))
            .unwrap_or_default();
        let mut text = format!("- state · {state}\n- acp · {acp}{protocol_line}\n");
        if let Some(auth) = auth_line {
            text.push_str(&format!("- auth · {auth}\n"));
        }
        text.push_str(&if self.session_bound {
            format!("- session · {}\n", self.session_id)
        } else {
            "- session · unbound\n".to_string()
        });
        if let Some(server) = &self.server_info {
            text.push_str(&format!("- server · {server}\n"));
        }
        text.push_str(&format!(
            "- model · {}{}\n\
             - agent · {}{}\n\
             - permission · {}\n\
             - plan · {}",
            self.cfg.model,
            effort_line,
            self.agent_label(&self.current_mode()),
            if self.modes.agent_preset.is_none() {
                " (default)"
            } else {
                ""
            },
            perm_label,
            if self.modes.plan { "on" } else { "off" },
        ));
        // Same popup surface as `/keys`, `/help` and `/session` (issue #53):
        // a status pushed into the transcript would be invisible behind the
        // welcome banner on a fresh start — the chat pane only draws the
        // banner while `show_banner` is set — and would pollute the
        // scrollback with facts that belong to the overlay.
        self.open_text_overlay(
            "builtin.status",
            self.locale.tr("Status", "状态").to_string(),
            text,
        );
    }
}

/// Compact token count: `1234` → `1.2K`, `1_500_000` → `1.5M`.
pub fn fmt_tokens(value: u64) -> String {
    if value < 1000 {
        value.to_string()
    } else if value < 1_000_000 {
        format!("{:.1}K", value as f64 / 1000.0)
    } else {
        format!("{:.1}M", value as f64 / 1_000_000.0)
    }
}

/// Compact duration: `1500ms` → `1.5s`, `135_000ms` → `2m15s`.
fn fmt_duration(ms: u64) -> String {
    if ms < 60_000 {
        format!("{:.1}s", ms as f64 / 1000.0)
    } else {
        format!("{}m{}s", ms / 60_000, (ms % 60_000) / 1000)
    }
}

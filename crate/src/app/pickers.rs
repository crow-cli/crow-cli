//! pickers: App methods for the pickers surface (Phase 2 split).

use super::*;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::bus::{AppEvent, Cmd};
use crate::controller::Controller;
use crate::input::Action;
use crate::transcript::NoticeLevel;

impl App {
    pub(crate) fn handle_picker_key(&mut self, key: KeyEvent, ctl: &Controller) {
        if self
            .picker
            .as_ref()
            .is_some_and(|picker| picker.kind == PickerKind::Theme)
            && matches!(
                crate::input::classify(
                    &key,
                    crate::input::KeyCtx {
                        input_empty: self.input.is_empty(),
                        history_active: self.input.hist_pos.is_some(),
                    },
                ),
                Some(Action::ToggleTheme)
            )
        {
            self.dispatch(Action::ToggleTheme, ctl);
            return;
        }
        let Some(picker) = &mut self.picker else {
            return;
        };
        let kind = picker.kind;
        let n = picker.items.len().max(1);
        // Page keys jump a screenful of the open popup (rows recorded by the
        // draw pass); they never wrap, unlike ↑/↓.
        let page = self.picker_page_rows.max(1);
        let sel_before = picker.sel;
        match key.code {
            KeyCode::Esc => self.picker = None,
            KeyCode::Up => picker.sel = picker.sel.checked_sub(1).unwrap_or(n - 1),
            KeyCode::Down => picker.sel = (picker.sel + 1) % n,
            KeyCode::PageUp => picker.sel = picker.sel.saturating_sub(page),
            KeyCode::PageDown => picker.sel = picker.sel.saturating_add(page).min(n - 1),
            KeyCode::Home => picker.sel = 0,
            KeyCode::End => picker.sel = n - 1,
            KeyCode::Enter => {
                let Some(item) = picker.items.get(picker.sel).cloned() else {
                    self.picker = None;
                    return;
                };
                let kind = picker.kind;
                self.picker = None;
                match kind {
                    PickerKind::Model => self.select_model(item, ctl),
                    PickerKind::Mode => self.set_mode(item.id, ctl),
                    PickerKind::Theme => self.select_palette(&item.id, ctl),
                    PickerKind::Harness => self.switch_harness(&item.id, ctl),
                    PickerKind::UiPlugin => {
                        ctl.send(Cmd::PluginUiSelected {
                            agent_id: self.session_id.clone(),
                            id: item.id,
                        });
                    }
                    PickerKind::Permission => self.set_permission(item.id, ctl),
                    PickerKind::Session => {
                        if self.resume_via_acp {
                            self.resume_acp_session(&item.id, ctl);
                        } else {
                            self.resume_session(&item.id, ctl);
                        }
                    }
                    PickerKind::Effort => {
                        let effort = item.id;
                        self.modes.effort = Some(effort.clone());
                        ctl.send(Cmd::SelectModel {
                            session_id: self.session_id.clone(),
                            provider: None,
                            model: None,
                            effort: Some(effort.clone()),
                        });
                        self.transcript.push_notice(
                            NoticeLevel::Info,
                            self.locale.trf(
                                "reasoning effort → {}",
                                "推理强度 → {}",
                                &[effort.clone()],
                            ),
                        );
                    }
                    PickerKind::Auth => self.start_auth(&item.id, ctl),
                    PickerKind::CordisPlugin => {
                        let action = self
                            .cordis_plugins
                            .iter()
                            .find(|plugin| plugin.id == item.id)
                            .map(|plugin| {
                                (
                                    plugin.id.clone(),
                                    plugin.status.clone(),
                                    plugin.approval_request_id.clone(),
                                )
                            });
                        if let Some((_plugin_id, _, Some(request_id))) = action.as_ref() {
                            self.open_cordis_approval_picker(request_id.clone());
                        } else if let Some((plugin_id, status, _)) = action {
                            if matches!(status.as_str(), "starting-host" | "client-pending") {
                                self.show_tip(self.locale.trf(
                                    "plugin {} is already starting",
                                    "插件 {} 已在启动中",
                                    &[plugin_id],
                                ));
                                return;
                            }
                            let enabled = !matches!(status.as_str(), "running" | "waiting");
                            ctl.send(Cmd::SetCordisPluginEnabled {
                                agent_id: self.session_id.clone(),
                                plugin_id: plugin_id.clone(),
                                enabled,
                            });
                            self.show_tip(if enabled {
                                self.locale.trf(
                                    "restoring plugin {}…",
                                    "正在恢复插件 {}…",
                                    &[plugin_id.clone()],
                                )
                            } else {
                                self.locale.trf(
                                    "stopping plugin {}…",
                                    "正在停止插件 {}…",
                                    &[plugin_id.clone()],
                                )
                            });
                        }
                    }
                    PickerKind::CordisApproval => {
                        if let Some(request_id) = item.provider {
                            ctl.send(Cmd::RespondCordisApproval {
                                request_id,
                                decision: item.id,
                            });
                        }
                    }
                    PickerKind::AgentHistory => self.select_agent_transcript(&item.id),
                }
            }
            _ => {}
        }
        // The theme dialog lives on its highlight: moving the selection
        // instantly applies the palette row under it, without waiting for
        // Enter. Enter above still closes and commits (Theme-Plugin load +
        // persisted preference); Esc just closes and keeps the preview.
        if kind == PickerKind::Theme
            && matches!(
                key.code,
                KeyCode::Up
                    | KeyCode::Down
                    | KeyCode::PageUp
                    | KeyCode::PageDown
                    | KeyCode::Home
                    | KeyCode::End
            )
            && self.picker.as_ref().is_some_and(|picker| {
                picker.kind == PickerKind::Theme && picker.sel != sel_before
            })
        {
            self.preview_picker_theme();
        }
    }

    /// Keyboard driving of the `/plugins` tree popup. The tree widget owns
    /// selection and viewport; ←/→ and enter fold/unfold a provider branch.
    pub(crate) fn handle_plugin_tree_key(&mut self, key: KeyEvent) {
        if key.modifiers != KeyModifiers::NONE {
            return;
        }
        if key.code == KeyCode::Esc {
            self.plugin_tree = None;
            return;
        }
        let Some(tree) = &mut self.plugin_tree else {
            return;
        };
        let page = self.plugin_tree_page_rows.max(1);
        match key.code {
            KeyCode::Up => {
                tree.state.key_up();
            }
            KeyCode::Down => {
                tree.state.key_down();
            }
            KeyCode::Left => {
                tree.state.key_left();
            }
            KeyCode::Right | KeyCode::Enter => {
                tree.state.toggle_selected();
            }
            KeyCode::PageUp => {
                tree.state
                    .select_relative(|i| i.map_or(0, |i| i.saturating_sub(page)));
            }
            KeyCode::PageDown => {
                tree.state
                    .select_relative(|i| i.map_or(0, |i| i.saturating_add(page)));
            }
            KeyCode::Home => {
                tree.state.select_first();
            }
            KeyCode::End => {
                tree.state.select_last();
            }
            _ => {}
        }
    }

    pub(crate) fn agent_navigation_ids(&self) -> Vec<String> {
        let mut ids = vec![self.session_id.clone()];
        ids.extend(
            self.subagents
                .iter()
                .filter(|view| self.subagent_in_current_batch(&view.id))
                .map(|view| view.id.clone()),
        );
        if self
            .subagents
            .iter()
            .any(|view| !self.subagent_in_current_batch(&view.id))
        {
            ids.push(AGENT_HISTORY_ID.into());
        }
        ids
    }

    pub(crate) fn begin_agent_navigation(&mut self) {
        if self.subagents.is_empty() {
            return;
        }
        self.agent_selection = Some(match self.active_subagent.as_deref() {
            Some(id) if !self.subagent_in_current_batch(id) => AGENT_HISTORY_ID.into(),
            Some(id) => id.into(),
            None => self.session_id.clone(),
        });
        self.needs_redraw = true;
    }

    pub(crate) fn move_agent_selection(&mut self, delta: isize) {
        let ids = self.agent_navigation_ids();
        if ids.len() < 2 {
            self.agent_selection = None;
            return;
        }
        let current = self
            .agent_selection
            .as_deref()
            .unwrap_or_else(|| self.active_subagent.as_deref().unwrap_or(&self.session_id));
        let index = ids.iter().position(|id| id == current).unwrap_or(0);
        let next = (index as isize + delta).rem_euclid(ids.len() as isize) as usize;
        self.agent_selection = Some(ids[next].clone());
        self.needs_redraw = true;
    }

    pub(crate) fn confirm_agent_selection(&mut self) {
        let Some(id) = self.agent_selection.take() else {
            return;
        };
        self.select_agent_transcript(&id);
    }

    pub(crate) fn cancel_agent_selection(&mut self) {
        self.agent_selection = None;
        self.needs_redraw = true;
    }

    pub(crate) fn select_agent_transcript(&mut self, id: &str) {
        self.agent_selection = None;
        if id == AGENT_HISTORY_ID {
            self.open_agent_history_picker();
            return;
        } else if id == self.session_id {
            self.active_subagent = None;
        } else if self.subagents.iter().any(|view| view.id == id) {
            self.active_subagent = Some(id.to_string());
        } else {
            return;
        }
        self.scroll_up = 0;
        self.sel = None;
    }

    pub(crate) fn open_agent_history_picker(&mut self) {
        let items = self
            .subagents
            .iter()
            .rev()
            .filter(|view| !self.subagent_in_current_batch(&view.id))
            .map(|view| PickerItem {
                id: view.id.clone(),
                label: view.label.clone(),
                meta: if view.running {
                    "running"
                } else if view.failed {
                    "failed"
                } else {
                    "completed"
                }
                .into(),
                provider: None,
            })
            .collect::<Vec<_>>();
        if items.is_empty() {
            return;
        }
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::AgentHistory,
            title: "Agent history".into(),
            sel: 0,
            items,
        });
        self.needs_redraw = true;
    }

    pub(crate) fn open_model_picker(&mut self, ctl: &Controller) {
        // Ask the ACP agent for its real catalog; seed the picker
        // with fallback presets / env snapshot meanwhile.
        ctl.send(Cmd::FetchCatalog {
            session_id: self.session_id.clone(),
        });
        let mut items: Vec<PickerItem> = MODEL_PRESETS
            .iter()
            .map(|s| s.to_string())
            .collect::<Vec<_>>()
            .into_iter()
            .map(|id| PickerItem {
                id: id.clone(),
                label: id,
                meta: String::new(),
                provider: None,
            })
            .collect();
        // The effective model (explicit pick → last streamed → configured
        // default) is the picker's "current": the highlight and the ✓ mark
        // land on the model the session is actually running (issue #102).
        let current = self.current_model();
        if !items.iter().any(|i| i.id == current) {
            items.insert(
                0,
                PickerItem {
                    id: current.clone(),
                    label: current.clone(),
                    meta: String::new(),
                    provider: None,
                },
            );
        }
        let current_provider = self.cfg.provider.clone();
        let sel = items
            .iter()
            .position(|i| {
                i.id == current
                    && i.provider
                        .as_deref()
                        .is_none_or(|provider| provider == current_provider)
            })
            // The running model may come from the transcript without a
            // provider: fall back to an id-only match rather than row 0.
            .or_else(|| items.iter().position(|i| i.id == current))
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Model,
            title: self
                .locale
                .tr(
                    " model · enter select · esc close ",
                    " 模型 · enter 选择 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    pub(crate) fn open_effort_picker(&mut self, efforts: Vec<String>, default: Option<String>) {
        let mut items: Vec<PickerItem> = efforts
            .into_iter()
            .map(|e| {
                let is_default = default.as_deref() == Some(e.as_str());
                PickerItem {
                    id: e.clone(),
                    label: e,
                    meta: if is_default {
                        self.locale.tr("default", "默认").into()
                    } else {
                        String::new()
                    },
                    provider: None,
                }
            })
            .collect();
        if items.is_empty() {
            items = ["off", "high", "max"]
                .iter()
                .map(|e| PickerItem {
                    id: e.to_string(),
                    label: e.to_string(),
                    meta: String::new(),
                    provider: None,
                })
                .collect();
        }
        // The highlight lands on the effort actually in effect (host-echoed
        // `config_option_update` / last `/effort`), falling back to the
        // model's advertised default, then the first row (issue #102).
        let sel = self
            .modes
            .effort
            .as_deref()
            .and_then(|effort| items.iter().position(|i| i.id == effort))
            .or_else(|| {
                default
                    .as_deref()
                    .and_then(|d| items.iter().position(|i| i.id == d))
            })
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Effort,
            title: self
                .locale
                .tr(
                    " reasoning effort · enter select · esc close ",
                    " 推理强度 · enter 选择 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    /// `/resume`: list this workspace's durable sessions in a picker
    /// (grok-build's session picker). Live ACP prefers `session/list`;
    /// `limit` is the `/resume n` count (most recent first).
    pub(crate) fn open_resume_picker(&mut self, limit: usize, ctl: &Controller) {
        if !self.demo && self.list_session {
            ctl.send(Cmd::ListSessions {
                requester_session_id: self.session_id.clone(),
                prefix: None,
                limit,
            });
            self.show_tip(self.locale.tr("listing ACP sessions…", "正在列出 ACP 会话…"));
            return;
        }
        if !self.demo {
            self.show_tip(self.locale.tr(
                "agent did not advertise session/list — listing local JSONL",
                "Agent 未声明 session/list —— 改为列出本地 JSONL",
            ));
        }
        self.open_local_resume_picker(limit);
    }

    pub(crate) fn open_local_resume_picker(&mut self, limit: usize) {
        self.resume_via_acp = false;
        let sessions = crate::sessions::list_sessions(
            &self.cfg.session_root,
            &self.cfg.workspace,
            &self.session_id,
            limit,
        );
        if sessions.is_empty() {
            self.transcript.push_notice(
                NoticeLevel::Info,
                self.locale.tr(
                    "no durable sessions for this workspace yet — finish a turn and /resume finds it",
                    "此工作区还没有持久会话 —— 完成一轮对话后 /resume 即可找回",
                )
                .into(),
            );
            return;
        }
        let items: Vec<PickerItem> = sessions
            .iter()
            .map(|s| session_picker_row(&s.id, s.title.as_deref(), Some(s), None))
            .collect();
        self.resume_candidates = sessions;
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Session,
            title: self
                .locale
                .tr(
                    " resume session · {n} sessions · enter select · esc close ",
                    " 恢复会话 · {n} 个会话 · enter 选择 · esc 关闭 ",
                )
                .replace("{n}", &items.len().to_string())
                .into(),
            sel: 0,
            items,
        });
    }

    /// Resume a durable session: replay its JSONL into the scrollback and
    /// point the next prompt at the same id — the runtime (or host mux)
    /// keeps appending to the same log.
    pub(crate) fn resume_session(&mut self, id_or_prefix: &str, ctl: &Controller) {
        if self.resume_candidates.is_empty() {
            self.resume_candidates = crate::sessions::list_sessions(
                &self.cfg.session_root,
                &self.cfg.workspace,
                &self.session_id,
                usize::MAX,
            );
        }
        let matches: Vec<crate::sessions::SessionSummary> = self
            .resume_candidates
            .iter()
            .filter(|s| s.id.starts_with(id_or_prefix))
            .cloned()
            .collect();
        let session = match matches.as_slice() {
            [one] => one.clone(),
            [] => {
                self.transcript.push_notice(
                    NoticeLevel::Warn,
                    self.locale.trf(
                        "no session matches “{}” — /resume lists them",
                        "没有会话匹配「{}」—— /resume 可列出全部",
                        &[id_or_prefix.into()],
                    ),
                );
                return;
            }
            many => match many.iter().find(|s| s.id == id_or_prefix) {
                Some(one) => one.clone(),
                None => {
                    self.transcript.push_notice(
                        NoticeLevel::Warn,
                        self.locale.trf(
                            "“{}” is ambiguous ({} matches) — /resume lists them",
                            "「{}」有 {} 个匹配，存在歧义 —— /resume 可列出全部",
                            &[id_or_prefix.into(), many.len().to_string()],
                        ),
                    );
                    return;
                }
            },
        };
        let events = match crate::sessions::read_session_events(&session.file) {
            Ok(events) => events,
            Err(err) => {
                self.transcript.push_notice(
                    NoticeLevel::Warn,
                    self.locale.trf(
                        "cannot read {}: {}",
                        "无法读取 {}：{}",
                        &[session.file.display().to_string(), format!("{err:#}")],
                    ),
                );
                return;
            }
        };

        if self.session_id != session.id {
            if let Some(tab) = self.tab_index_of(&session.id) {
                // Already open in a tab — switching to it is the resume.
                // The view path (not the raw switch) releases compositor-
                // owned overlays with their cancel events first, exactly
                // like a tab click; a raw switch would leak the plugin's
                // single-overlay slot and float the popup onto the tab.
                self.switch_view_to_tab(tab, ctl);
                self.resume_candidates = Vec::new();
                self.transcript.push_notice(
                    NoticeLevel::Info,
                    self.locale.trf(
                        "⟲ {} is already open — switched to its tab",
                        "⟲ {} 已在打开的标签页中 —— 已切换过去",
                        &[session.id.clone()],
                    ),
                );
                return;
            }
            // Park the live session and replay into a fresh tab (issue #94).
            self.open_new_session(session.id.clone(), true);
        } else {
            self.reset_subagent_views();
            self.transcript.clear();
            self.transcript.set_root_session(session.id.clone());
            // Replay folds the session's own authoritative mode facts from empty.
            self.modes = Modes::default();
            self.queued = 0;
            self.prompt_queue.clear();
            self.queue_selection = None;
            self.queue_edit = None;
            self.pending_steer_cells.clear();
            self.prompt_pending = false;
            self.sel = None;
        }
        // The resumed stream's own model is the truth for the chip.
        self.selected_model = None;
        self.show_banner = false;
        let mut replayed = 0usize;
        for ev in &events {
            if ev.get("type").and_then(serde_json::Value::as_str) == Some("session") {
                continue; // header line
            }
            // Live, the TUI echoes user prompts locally and the event parser
            // skips them; on replay the log is the only source, so push here.
            if let Some(text) = crate::sessions::user_text(ev) {
                self.transcript.push_user(text, false);
                replayed += 1;
                continue;
            }
            self.handle(
                AppEvent::Rpc {
                    method: "session.event".into(),
                    params: serde_json::json!({ "sessionId": session.id, "event": ev }),
                },
                ctl,
            );
            replayed += 1;
        }
        self.state = RunState::Idle;
        self.run_started = None;
        self.scroll_up = 0;
        self.resume_candidates = Vec::new();
        self.transcript.push_notice(
            NoticeLevel::Info,
            self.locale.trf(
                "⟲ resumed {} · {} turn{} · {} events replayed — the next prompt continues it",
                "⟲ 已恢复 {} · {} 轮对话 · 回放 {} 个事件 —— 下一条消息继续它",
                &[
                    session.id.clone(),
                    session.turns.to_string(),
                    if session.turns == 1 { "" } else { "s" }.to_string(),
                    replayed.to_string(),
                ],
            ),
        );
        self.needs_redraw = true;
    }
}

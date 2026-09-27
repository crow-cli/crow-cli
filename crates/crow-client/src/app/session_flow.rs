//! session_flow: App methods for the session_flow surface (Phase 2 split).

use super::*;
use crate::bus::{Cmd, SessionListItem};
use crate::controller::Controller;
use crate::transcript::NoticeLevel;

impl App {
    /// The `/new` flow, shared by the slash command and the tab strip `+`
    /// cell: reuse an empty tab, otherwise park the conversation in its tab.
    pub(crate) fn new_session_flow(&mut self, arg: &str, ctl: &Controller) {
        if self.demo {
            let id = if arg.is_empty() {
                format!("crow-{}", timestamp())
            } else {
                arg.to_string()
            };
            self.prepare_new_session(id.clone(), true, ctl);
            ctl.send(Cmd::FetchSkills {
                session_id: self.session_id.clone(),
            });
            self.transcript.push_notice(
                NoticeLevel::Info,
                self.locale.trf(
                    "new session · {} — /agent picks its agent preset",
                    "新会话 · {} —— /agent 选择它的 Agent 预设",
                    &[id],
                ),
            );
        } else {
            // A local placeholder ids the tab until session/new resolves —
            // the same shape main.rs seeds the startup session with. The
            // real id lands on this tab via `awaiting_binds` at SessionBound.
            let placeholder = format!("crow-{}", timestamp());
            self.prepare_new_session(placeholder.clone(), false, ctl);
            self.awaiting_binds.push_back(AwaitingBind {
                id: placeholder.clone(),
                open: true,
            });
            ctl.send(Cmd::NewSession { requester: Some(placeholder) });
            self.show_tip(self.locale.tr("session/new …", "正在创建会话（session/new）…"));
        }
    }

    pub(crate) fn prepare_new_session(&mut self, id: String, bound: bool, ctl: &Controller) {
        let empty = !self.prompt_pending && self.state != RunState::Running
            && self.prompt_queue.is_empty()
            && self.transcript.cells.iter().all(|cell| matches!(cell.kind, crate::transcript::CellKind::Notice { .. }));
        if !empty {
            self.open_new_session(id, bound);
            return;
        }
        let old = self.take_live_slot();
        if !self.startup_bound && !old.session_bound
            && !self.awaiting_binds.iter().any(|entry| entry.id == old.id)
        {
            self.startup_bound = true;
            self.awaiting_binds.push_front(AwaitingBind { id: old.id.clone(), open: false });
        }
        // Keep outstanding bind requests in FIFO order, but discard their late results.
        for awaiting in &mut self.awaiting_binds {
            if awaiting.id == old.id { awaiting.open = false; }
        }
        ctl.send(Cmd::ForgetSession { session_id: old.id });
        let mut fresh = SessionSlot::fresh(id, bound);
        fresh.transcript.locale = self.locale;
        fresh.input = old.input;
        fresh.pending_images = old.pending_images;
        fresh.input_expanded = old.input_expanded;
        self.put_live_slot(fresh);
        self.after_switch();
    }

    /// The `/close` flow (issue #94): stop viewing the current session tab
    /// and drop everything bound to it (transcript, composer draft, queue,
    /// asks, subagents). Local only — ACP has no session/close, so the
    /// server-side session keeps existing; acp.rs forgets its turn state
    /// and queued prompts so nothing more is sent into the void, and the
    /// session's later updates drop at the router. An in-flight turn keeps
    /// running and is dropped when it settles. Never closes the last tab.
    pub(crate) fn close_session_flow(&mut self, ctl: &Controller) {
        let total = self.session_tab_count();
        if total < 2 {
            self.show_tip(self.locale.tr(
                "cannot close the last session — /new opens another first",
                "不能关闭最后一个会话 —— 先用 /new 开一个新的",
            ));
            return;
        }
        let doomed = self.session_id.clone();
        let running = self.state != RunState::Idle || self.prompt_pending;
        // Compositor-owned overlays (plugin view/select/slider) must be
        // released with a cancel event before the tab dies — the same path
        // a tab click takes. Painter popups, asks and the composer draft
        // die with the slot (ask overlays auto-cancel through Drop).
        self.cancel_plugin_overlays(ctl);
        let doomed_slot = self.take_live_slot();
        let discarded = doomed_slot.prompt_queue.len();
        let had_draft = !doomed_slot.input.is_empty()
            || !doomed_slot.pending_images.is_empty();
        let had_ask =
            doomed_slot.permission_ask.is_some() || doomed_slot.elicitation_ask.is_some();
        drop(doomed_slot);

        // The bind this tab may still be awaiting keeps its FIFO position
        // (the in-flight session/new·resume owns it) but is now dead: when
        // it resolves the session is forgotten, never bound onto a
        // neighboring tab.
        if let Some(entry) = self.awaiting_binds.iter_mut().find(|entry| entry.id == doomed) {
            entry.open = false;
        }
        // Forget the session on the ACP side too: drop its turn state and
        // queued prompts (no-op for an unbound placeholder id).
        ctl.send(Cmd::ForgetSession {
            session_id: doomed.clone(),
        });

        // View a neighbor first, keeping the closed tab's conceptual slot:
        // the right neighbor when one exists, else the tab on the left.
        let right = self.current + 1 < total;
        let pidx = if right { self.current } else { self.current - 1 };
        let mut target = self.parked.remove(pidx);
        target.completed_unseen = false;
        self.current = if right {
            self.current
        } else {
            self.current.saturating_sub(1)
        };
        self.put_live_slot(target);
        self.after_switch();
        self.needs_redraw = true;

        let label = short_id(&doomed);
        let mut bits: Vec<String> = Vec::new();
        if running {
            bits.push("its running turn keeps settling".into());
        }
        if discarded > 0 {
            bits.push(format!("{discarded} queued dropped"));
        }
        if had_draft {
            bits.push("draft dropped".into());
        }
        if had_ask {
            bits.push("pending ask cancelled".into());
        }
        if bits.is_empty() {
            self.show_tip(self.locale.trf("closed {}", "已关闭 {}", &[label.clone()]));
        } else {
            self.show_tip(self.locale.trf(
                "closed {} · {}",
                "已关闭 {} · {}",
                &[label.clone(), bits.join(", ")],
            ));
        }
    }

    pub(crate) fn set_session_connection(&mut self, connection: crate::bus::SessionConnection) {
        self.server_info = connection.server;
        self.auth = connection.auth;
        self.load_session = connection.load_session;
        self.list_session = connection.list_session;
        self.resume_session_cap = connection.resume_session;
    }

    pub(crate) fn reset_session_ui(&mut self) {
        self.reset_subagent_views();
        self.transcript.clear();
        self.modes = Modes::default();
        self.skills.clear();
        self.last_presets.clear();
        self.last_models.clear();
        self.permission_choices.clear();
        self.effort_choices.clear();
        self.selected_model = None;
        self.session_model = None;
        self.session_provider = None;
        self.session_title = None;
        self.show_banner = false;
        self.queued = 0;
        self.prompt_queue.clear();
        self.queue_selection = None;
        self.queue_edit = None;
        self.pending_steer_cells.clear();
        self.prompt_pending = false;
        self.sel = None;
        self.state = RunState::Idle;
        self.run_started = None;
        self.scroll_up = 0;
        self.resume_candidates = Vec::new();
        self.resume_via_acp = false;
        self.session_bound = self.demo;
    }

    pub(crate) fn reset_subagent_views(&mut self) {
        self.subagents.clear();
        self.current_subagents.clear();
        self.next_subagent_starts_batch = true;
        self.active_subagent = None;
        self.agent_selection = None;
    }

    pub(crate) fn resume_acp_session(&mut self, id: &str, ctl: &Controller) {
        // The welcome banner only ever paints instead of the transcript, so
        // any path that (re)loads real history must dismiss it — the local
        // `resume_session` does the same. Without this, a /resume before the
        // first prompt left the banner covering the whole replayed chat.
        // Dismissed *after* the branch: a fresh tab starts with the banner
        // (composer chrome is tab-bound), and the same-session branch resets
        // its own fields.
        if self.session_id == id {
            // Resuming the viewed session: reset its UI and re-stream. The
            // resume still re-binds on the ACP side (acp.rs emits
            // SessionBound unconditionally), so this tab keeps a FIFO
            // entry — without it a concurrent /new's SessionBound would
            // be consumed by this bind and the tabs would cross-bind.
            self.reset_session_ui();
            self.session_id = id.to_string();
            self.transcript.set_root_session(id.to_string());
            self.awaiting_binds.push_back(AwaitingBind {
                id: id.to_string(),
                open: true,
            });
        } else if let Some(tab) = self.tab_index_of(id) {
            // Already open in a tab — switching to it is the resume. Same
            // as the local path: release plugin overlays on the way out.
            self.switch_view_to_tab(tab, ctl);
            return;
        } else {
            // Park the live session; the resumed session binds this fresh
            // tab. With ACP `session/resume` the agent does not replay the
            // transcript; the legacy `session/load` fallback streams it via
            // session/update tagged with this id.
            self.open_new_session(id.to_string(), false);
            self.awaiting_binds.push_back(AwaitingBind {
                id: id.to_string(),
                open: true,
            });
        }
        self.show_banner = false;
        ctl.send(Cmd::ResumeSession {
            session_id: id.to_string(),
        });
        self.show_tip(self.locale.trf("resuming {} …", "正在恢复会话 {} …", &[id.into()]));
        self.needs_redraw = true;
    }

    pub(crate) fn on_acp_session_list(
        &mut self,
        requester_session_id: String,
        sessions: Vec<SessionListItem>,
        prefix: Option<String>,
        limit: usize,
        ctl: &Controller,
    ) {
        if requester_session_id != self.session_id {
            return;
        }
        let skip = self.session_id.clone();
        // The `/resume n` cap counts resumable sessions only: the current
        // session is dropped first, then the list truncates to the limit.
        let mut sessions: Vec<SessionListItem> = sessions
            .into_iter()
            .filter(|s| s.id != skip)
            .collect();
        sessions.truncate(limit);
        if let Some(prefix) = prefix.as_deref().filter(|p| !p.is_empty()) {
            match unique_session_list_match(&sessions, prefix) {
                Ok(id) => {
                    self.resume_acp_session(&id, ctl);
                    return;
                }
                Err(msg) => {
                    self.transcript.push_notice(NoticeLevel::Warn, msg);
                    if sessions.is_empty() {
                        return;
                    }
                }
            }
        }
        if sessions.is_empty() {
            self.transcript.push_notice(
                NoticeLevel::Info,
                self.locale.tr(
                    "no ACP sessions from session/list — finish a turn and /resume finds it",
                    "session/list 没有返回 ACP 会话 —— 完成一轮对话后 /resume 即可找回",
                )
                .into(),
            );
            return;
        }
        // Local JSONL summaries (turns, age, prompt preview) for the same
        // workspace; the local log is the only source for those fields.
        let local_by_id: std::collections::HashMap<String, crate::sessions::SessionSummary> =
            crate::sessions::list_sessions(
                &self.cfg.session_root,
                &self.cfg.workspace,
                &self.session_id,
                usize::MAX,
            )
            .into_iter()
            .map(|s| (s.id.clone(), s))
            .collect();
        let items: Vec<PickerItem> = sessions
            .iter()
            .map(|s| {
                let local = local_by_id.get(&s.id);
                let title = s
                    .title
                    .clone()
                    .filter(|t| !t.is_empty())
                    .or_else(|| local.and_then(|l| l.title.clone()));
                session_picker_row(&s.id, title.as_deref(), local, s.updated_at.as_deref())
            })
            .collect();
        self.resume_via_acp = true;
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

    pub(crate) fn on_acp_session_list_unavailable(
        &mut self,
        requester_session_id: String,
        prefix: Option<String>,
        limit: usize,
        error: String,
        ctl: &Controller,
    ) {
        if requester_session_id != self.session_id {
            return;
        }
        self.show_tip(self.locale.trf(
            "session/list unavailable ({}) — listing local JSONL",
            "session/list 不可用（{}）—— 改为列出本地 JSONL",
            &[error.clone()],
        ));
        if let Some(prefix) = prefix.filter(|p| !p.is_empty()) {
            if self.resume_session_cap || self.load_session {
                self.resume_acp_session(&prefix, ctl);
                return;
            }
            self.resume_session(&prefix, ctl);
            return;
        }
        self.open_local_resume_picker(limit);
        if self.resume_session_cap || self.load_session {
            self.resume_via_acp = true;
        }
    }
}

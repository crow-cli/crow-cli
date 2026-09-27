//! pump: App methods for the pump surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crossterm::event::{Event, KeyEventKind};
use crate::bus::{AppEvent, Cmd, CtlEvent};
use crate::controller::Controller;
use crate::events::parse_notification;
use crate::transcript::NoticeLevel;

impl App {
    pub fn handle(&mut self, ev: AppEvent, ctl: &Controller) {
        // Cheap fingerprints instead of full snapshot clones: chatty agents
        // can stream hundreds of thousands of session updates (issue #94 —
        // a session/load replay storm), and cloning every queue/agents
        // snapshot per event multiplies that into a UI-melting alloc storm.
        let queue_before = (!self.demo).then(|| self.queue_fingerprint());
        let agents_before = (!self.demo).then(|| self.agents_fingerprint());
        let active_before = (!self.demo).then(|| (self.session_id.clone(), self.session_bound));
        self.handle_inner(ev, ctl);
        // Previewed palettes never stick: after every event, a preview that
        // is no longer under a highlight (and whose Enter commit is not
        // still loading) reverts the painter to the committed theme.
        self.reconcile_theme_preview();
        // A turn ran on the picked model → the stream is the truth again.
        if self.selected_model.is_some()
            && self.selected_model.as_deref() == self.transcript.last_model.as_deref()
        {
            self.selected_model = None;
        }
        if let Some(before) = queue_before {
            if self.queue_fingerprint() != before {
                ctl.send(Cmd::QueueSnapshot {
                    snapshot: self.queue_snapshot(),
                });
            }
        }
        if let Some(before) = agents_before {
            if self.agents_fingerprint() != before {
                ctl.send(Cmd::AgentsSnapshot {
                    snapshot: self.agents_snapshot(),
                });
            }
        }
        if let Some(before) = active_before {
            if (self.session_id.as_str(), self.session_bound) != (before.0.as_str(), before.1) {
                ctl.send(Cmd::ActiveSession {
                    session_id: self.session_bound.then(|| self.session_id.clone()),
                });
            }
        }
    }

    /// Identity of everything `queue_snapshot` projects, without the summary
    /// strings: ordered prompt ids (order captures reordering) plus the
    /// selection/edit/confirm flags. A summary edit always passes through an
    /// `editing_id` transition, so text changes are covered too.
    pub(crate) fn queue_fingerprint(&self) -> (Vec<u64>, Option<u64>, Option<u64>, bool) {
        (
            self.prompt_queue.iter().map(|prompt| prompt.id).collect(),
            self.queue_selection
                .and_then(|index| self.prompt_queue.get(index))
                .map(|prompt| prompt.id),
            self.queue_edit.as_ref().map(|edit| edit.prompt_id),
            self.queue_delete_confirming(),
        )
    }

    /// Identity of everything `agents_snapshot` projects, without label
    /// strings: root running bit, per-view id/status/current, the history
    /// count, and the active/selected ids. Labels are assigned at view
    /// creation, so they cannot change without the id set changing.
    pub(crate) fn agents_fingerprint(&self) -> (String, Option<String>, bool, Vec<(String, u8, bool)>, usize) {
        let active_id = match self.active_subagent.as_deref() {
            Some(id) if !self.subagent_in_current_batch(id) => AGENT_HISTORY_ID.into(),
            Some(id) => id.into(),
            None => self.session_id.clone(),
        };
        let root_running = !matches!(self.state, RunState::Idle) || self.prompt_pending;
        let views: Vec<(String, u8, bool)> = self
            .subagents
            .iter()
            .map(|view| {
                let status = if view.running {
                    0
                } else if view.failed {
                    1
                } else {
                    2
                };
                (
                    view.id.clone(),
                    status,
                    self.subagent_in_current_batch(&view.id),
                )
            })
            .collect();
        let history_count = self
            .subagents
            .iter()
            .filter(|view| !self.subagent_in_current_batch(&view.id))
            .count();
        let selected_id = self.agent_selection.as_ref().and_then(|selected| {
            (self.subagents.iter().any(|view| view.id == *selected)
                || *selected == self.session_id
                || (history_count > 0 && selected == AGENT_HISTORY_ID))
                .then(|| selected.clone())
        });
        (active_id, selected_id, root_running, views, history_count)
    }

    pub(crate) fn queue_snapshot(&self) -> crate::bus::QueueSnapshot {
        let editing_id = self.queue_edit.as_ref().map(|edit| edit.prompt_id);
        let selected_id = self
            .queue_selection
            .and_then(|index| self.prompt_queue.get(index))
            .map(|prompt| prompt.id);
        crate::bus::QueueSnapshot {
            count: self.prompt_queue.len(),
            items: self
                .queue_previews(0)
                .into_iter()
                .map(|preview| crate::bus::QueueSnapshotItem {
                    id: preview.id,
                    ordinal: preview.ordinal,
                    summary: preview.summary,
                })
                .collect(),
            selected_id,
            editing_id,
            delete_confirm: self.queue_delete_confirming(),
        }
    }

    pub(crate) fn agents_snapshot(&self) -> crate::bus::AgentsSnapshot {
        let active_id = match self.active_subagent.as_deref() {
            Some(id) if !self.subagent_in_current_batch(id) => AGENT_HISTORY_ID.into(),
            Some(id) => id.into(),
            None => self.session_id.clone(),
        };
        let root_running = !matches!(self.state, RunState::Idle) || self.prompt_pending;
        let mut items = vec![crate::bus::AgentsSnapshotItem {
            id: self.session_id.clone(),
            label: self.locale.tr("main", "主会话").into(),
            kind: "main".into(),
            status: if root_running { "running" } else { "idle" }.into(),
            current: false,
        }];
        items.extend(self.subagents.iter().map(|view| {
            crate::bus::AgentsSnapshotItem {
                id: view.id.clone(),
                label: view.label.clone(),
                kind: "subagent".into(),
                status: if view.running {
                    "running"
                } else if view.failed {
                    "failed"
                } else {
                    "finished"
                }
                .into(),
                current: self.subagent_in_current_batch(&view.id),
            }
        }));
        let history_count = self
            .subagents
            .iter()
            .filter(|view| !self.subagent_in_current_batch(&view.id))
            .count();
        if history_count > 0 {
            items.push(crate::bus::AgentsSnapshotItem {
                id: AGENT_HISTORY_ID.into(),
                label: format!("History ({history_count})"),
                kind: "history".into(),
                status: "idle".into(),
                current: false,
            });
        }
        let selected_id = self.agent_selection.as_ref().and_then(|selected| {
            items
                .iter()
                .any(|item| item.id == *selected)
                .then(|| selected.clone())
        });
        crate::bus::AgentsSnapshot {
            active_id,
            selected_id,
            items,
        }
    }

    pub(crate) fn subagent_in_current_batch(&self, id: &str) -> bool {
        self.current_subagents.is_empty() || self.current_subagents.contains(id)
    }

    pub(crate) fn handle_inner(&mut self, ev: AppEvent, ctl: &Controller) {
        match ev {
            AppEvent::Terminate => {
                self.quit = true;
            }
            AppEvent::Term(term) => self.handle_term(term, ctl),
            AppEvent::Ui(ui) => {
                let idle_session = match &ui {
                    crate::events::UiEvent::SessionStatus {
                        session,
                        running: false,
                    } if self.session_was_running(session) => Some(session.clone()),
                    _ => None,
                };
                self.apply_ui(ui);
                if let Some(session) = idle_session {
                    self.dispatch_session_queue(&session, ctl);
                }
            }
            AppEvent::Rpc { method, params } => {
                if method == crate::cordis::AGENTS_NAVIGATE {
                    let protocol = params.get("protocol").and_then(serde_json::Value::as_u64);
                    let action = params.get("action").and_then(serde_json::Value::as_str);
                    if protocol == Some(crate::cordis::PROTOCOL) {
                        match action {
                            Some("begin") => self.begin_agent_navigation(),
                            Some("previous") => self.move_agent_selection(-1),
                            Some("next") => self.move_agent_selection(1),
                            Some("confirm") => self.confirm_agent_selection(),
                            Some("cancel") => self.cancel_agent_selection(),
                            _ => {}
                        }
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::AGENTS_SELECT {
                    let protocol = params.get("protocol").and_then(serde_json::Value::as_u64);
                    let id = params.get("id").and_then(serde_json::Value::as_str);
                    if protocol == Some(crate::cordis::PROTOCOL) {
                        if let Some(id) = id {
                            self.select_agent_transcript(id);
                        }
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::UI_UPDATE {
                    match serde_json::from_value::<UiPluginCatalog>(params) {
                        Ok(catalog) if catalog.protocol == 0 => self.ui_plugins = catalog.plugins,
                        Ok(_) => {}
                        Err(err) => self.show_tip(self.locale.trf(
                            "UI Plugin catalog ignored: {}",
                            "已忽略 UI 插件目录：{}",
                            &[err.to_string()],
                        )),
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::APPROVALS_UPDATE {
                    match serde_json::from_value::<CordisApprovalsSnapshot>(params) {
                        Ok(snapshot) if snapshot.protocol == 0 => {
                            self.pending_cordis_approvals = snapshot.approvals;
                        }
                        Ok(_) => {}
                        Err(err) => self.show_tip(self.locale.trf(
                            "plugin approvals ignored: {}",
                            "已忽略插件授权：{}",
                            &[err.to_string()],
                        )),
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::THEME_UPDATE {
                    self.apply_palette_rpc(&params);
                    return;
                }
                if method == crate::cordis::THEME_REMOVE {
                    self.remove_palette_rpc(&params);
                    return;
                }
                if method == crate::cordis::COMMANDS_UPDATE {
                    match serde_json::from_value::<PluginCommandCatalog>(params) {
                        Ok(catalog) if catalog.protocol == 0 => {
                            self.plugin_commands = catalog.commands;
                        }
                        Ok(_) => {}
                        Err(err) => self.show_tip(self.locale.trf(
                            "commands ignored: {}",
                            "已忽略命令：{}",
                            &[err.to_string()],
                        )),
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::OVERLAY_UPDATE {
                    match serde_json::from_value::<PluginOverlaySnapshot>(params) {
                        Ok(snapshot) if snapshot.protocol == 0 => match snapshot.overlay {
                            Some(PluginOverlay::Select(mut select)) => {
                                if let Some(sel) = select_initial_index(&select) {
                                    select.sel = sel;
                                    if let Some(previous) = self.select_overlay.as_ref()
                                        .filter(|previous| previous.id == select.id) {
                                        if select.searchable { select.query = previous.query.clone(); }
                                        if let Some(index) = select.options.iter()
                                            .position(|option| option.value == previous.value) {
                                            select.sel = index;
                                        }
                                        // A refreshed catalog can move, remove or rename rows.
                                        // Keep the user's filter and stable choice when visible;
                                        // otherwise select a real matching option, never a header.
                                        select.reconcile_search();
                                    }
                                    self.slider_overlay = None;
                                    self.view_overlay = None;
                                    self.select_overlay = Some(select);
                                } else {
                                    self.show_tip(self.locale.tr(
                                        "overlay ignored: invalid select",
                                        "已忽略 overlay：无效的 select",
                                    ));
                                    self.slider_overlay = None;
                                    self.select_overlay = None;
                                    self.view_overlay = None;
                                }
                            }
                            Some(PluginOverlay::Slider(mut slider))
                                if !slider.id.is_empty()
                                    && slider.min.is_finite()
                                    && slider.max.is_finite()
                                    && slider.step.is_finite()
                                    && slider.value.is_finite()
                                    && slider.min < slider.max
                                    && slider.step > 0.0
                                    && (!slider.snap_to_marks || !slider.marks.is_empty())
                                    && slider.marks.iter().all(|mark| {
                                        mark.value.is_finite()
                                            && mark.value >= slider.min
                                            && mark.value <= slider.max
                                            && !mark.label.is_empty()
                                    }) =>
                            {
                                slider.value = slider.value.clamp(slider.min, slider.max);
                                self.select_overlay = None;
                                self.view_overlay = None;
                                self.slider_overlay = Some(slider);
                            }
                            Some(PluginOverlay::Slider(_)) => {
                                self.show_tip(self.locale.tr(
                                    "overlay ignored: invalid slider",
                                    "已忽略 overlay：无效的 slider",
                                ));
                                self.slider_overlay = None;
                                self.select_overlay = None;
                                self.view_overlay = None;
                            }
                            Some(PluginOverlay::View(mut view))
                                if !view.id.is_empty()
                                    && !view.title.is_empty()
                                    && crate::slots::validate_node_tree(&view.nodes).is_ok() =>
                            {
                                view.notify_plugin = true;
                                self.slider_overlay = None;
                                self.select_overlay = None;
                                self.view_overlay = Some(view);
                            }
                            Some(PluginOverlay::View(_)) => {
                                self.show_tip(self.locale.tr(
                                    "overlay ignored: invalid view",
                                    "已忽略 overlay：无效的 view",
                                ));
                                self.slider_overlay = None;
                                self.select_overlay = None;
                                self.view_overlay = None;
                            }
                            None => {
                                // The plugin's overlay closed (dispatch ack
                                // or plugin-side close). Only compositor
                                // surfaces go with it: a painter popup that
                                // was parked/restored by a tab switch in the
                                // meantime must survive the ack.
                                self.slider_overlay = None;
                                self.select_overlay = None;
                                if self
                                    .view_overlay
                                    .as_ref()
                                    .is_some_and(|view| view.notify_plugin)
                                {
                                    self.view_overlay = None;
                                }
                            }
                        },
                        Ok(_) => {}
                        Err(err) => self.show_tip(self.locale.trf(
                            "overlay ignored: {}",
                            "已忽略 overlay：{}",
                            &[err.to_string()],
                        )),
                    }
                    self.needs_redraw = true;
                    return;
                }
                if method == crate::cordis::SLOTS_UPDATE {
                    match crate::slots::parse_snapshot(&params) {
                        Ok(Some(snapshot)) => {
                            let stale = self.slot_snapshots.get(&snapshot.slot).is_some_and(|current| {
                                matches!((snapshot.rev, current.rev), (Some(next), Some(previous)) if next <= previous)
                            });
                            if !stale {
                                if snapshot.slot == "conversation.harness" {
                                    self.harness_badge = crate::harness_badge::parse(&snapshot);
                                }
                                self.slot_snapshots.insert(snapshot.slot.clone(), snapshot);
                            }
                        }
                        Ok(None) => {}
                        Err(err) => self.show_tip(self.locale.trf(
                            "slot ignored: {}",
                            "已忽略 slot：{}",
                            &[err.to_string()],
                        )),
                    }
                    self.needs_redraw = true;
                    return;
                }
                for ui in parse_notification(&method, &params) {
                    let idle_session = match &ui {
                        crate::events::UiEvent::SessionStatus {
                            session,
                            running: false,
                        } if self.session_was_running(session) => Some(session.clone()),
                        _ => None,
                    };
                    self.apply_ui(ui);
                    if let Some(session) = idle_session {
                        self.dispatch_session_queue(&session, ctl);
                    }
                }
                // apply_ui decides whether a fact affects the visible
                // frame; background chunks and unknown notifications do not.
            }
            AppEvent::RuntimeStderr(_line) => {
                // kept in proto's tail buffer for diagnostics; stay quiet here
            }
            AppEvent::RuntimeExited(code) => {
                // A next prompt restarts the runtime; its fresh startup
                // bind is again an unrequested one (see `startup_bound`).
                self.clear_delivery_state();
                if let Some(c) = code {
                    if c != 0 {
                    self.transcript.push_notice(
                        NoticeLevel::Warn,
                        self.locale.trf(
                            "runtime exited with code {} — next prompt restarts it",
                            "运行时以退出码 {} 结束 —— 下一条提示会重启它",
                            &[c.to_string()],
                        ),
                    );
                    }
                }
                self.needs_redraw = true;
            }
            AppEvent::Ctl(ctl_ev) => {
                match ctl_ev {
                    CtlEvent::NewSessionRequested => self.new_session_flow("", ctl),
                    CtlEvent::SessionBoundTo { previous_id, session_id, notice } => {
                        self.awaiting_binds.retain(|entry| entry.id != previous_id);
                        if self.session_id == previous_id || self.parked.iter().any(|slot| slot.id == previous_id) {
                            self.awaiting_binds.push_front(AwaitingBind { id: previous_id, open: true });
                            self.handle_inner(AppEvent::Ctl(CtlEvent::SessionBound { session_id, notice }), ctl);
                        } else {
                            ctl.send(Cmd::ForgetSession { session_id });
                        }
                    }
                    CtlEvent::BindFailedTo { previous_id, message } => {
                        self.awaiting_binds.retain(|entry| entry.id != previous_id);
                        // A failed empty tab must show its error, not the welcome page.
                        if self.session_id == previous_id {
                            self.show_banner = false;
                            self.show_tip(self.locale.tr("session creation failed · /new to retry", "会话创建失败 · /new 重试"));
                        }
                        else if let Some(slot) = self.parked.iter_mut().find(|slot| slot.id == previous_id) {
                            slot.show_banner = false;
                        }
                        self.handle_inner(AppEvent::Ctl(CtlEvent::SessionError { session_id: previous_id, message }), ctl);
                    }
                    CtlEvent::SessionConnection { session_id, connection } => {
                        if session_id == self.session_id {
                            self.set_session_connection(connection);
                        } else if let Some(slot) = self.parked.iter_mut().find(|slot| slot.id == session_id) {
                            slot.connection = Some(connection);
                        }
                    },
                    CtlEvent::Starting { runtime } => {
                        self.connection_error = None;
                        self.state = RunState::Starting;
                        self.run_started = Some(Instant::now());
                        self.state_note = if runtime == "harness" {
                            "switching Harness".into()
                        } else {
                            "starting runtime".into()
                        };
                    }
                    CtlEvent::Initialized { server, protocol } => {
                        self.server_info = Some(server);
                        self.protocol_tag = Some(protocol);
                    }
                    CtlEvent::Ready { server } => {
                        self.connection_error = None;
                        self.server_info = Some(server.clone());
                        if !self.prompt_pending {
                            self.state = RunState::Idle;
                            self.run_started = None;
                            self.state_note.clear();
                        }
                    }
                    CtlEvent::ConnectionFailed { target, error } => {
                        if !target.is_empty() { self.server_info = Some(target); }
                        if self.server_info.is_none() { self.server_info = Some("ACP".into()); }
                        self.connection_error = Some(error.clone());
                        self.session_id = "unavailable".into();
                        self.session_bound = false;
                        self.session_model = None;
                        self.selected_model = None;
                        self.auth = crate::acp_auth::AuthSnapshot::none();
                        self.prompt_pending = false;
                        self.state = RunState::Idle;
                        self.run_started = None;
                        self.state_note.clear();
                        self.transcript.push_notice(NoticeLevel::Error, error);
                    }
                    CtlEvent::PromptQueued {
                        session_id: Some(sid),
                        ..
                    } => {
                        // Per-session: only the session the prompt belongs
                        // to settles — a background tab's prompt must not
                        // flip the viewed tab out of Starting.
                        if sid == self.session_id {
                            self.prompt_pending = false;
                            if self.state == RunState::Starting {
                                self.state = RunState::Running;
                            }
                            self.state_note.clear();
                        } else if let Some(slot) =
                            self.parked.iter_mut().find(|slot| slot.id == *sid)
                        {
                            slot.prompt_pending = false;
                        }
                    }
                    CtlEvent::PromptQueued { session_id: None, .. } => {
                        // Legacy attach transport: no session attribution,
                        // settle the viewed tab as before.
                        self.prompt_pending = false;
                        if self.state == RunState::Starting {
                            self.state = RunState::Running;
                        }
                        self.state_note.clear();
                    }
                    CtlEvent::SteerSettled {
                        message_id,
                        deferred,
                    } => {
                        self.settle_steer(message_id, deferred);
                    }
                    CtlEvent::Error(err) => {
                        // Connection-level failure (no session context): the
                        // notice belongs to the viewed tab. Session-scoped
                        // failures arrive as `SessionError` instead.
                        self.prompt_pending = false;
                        self.state = RunState::Idle;
                        self.run_started = None;
                        self.transcript.push_notice(NoticeLevel::Error, err);
                        self.dispatch_next_queued(ctl);
                    }
                    CtlEvent::SessionOpFailed { session_id, message } => {
                        if session_id == self.session_id {
                            self.transcript.push_notice(NoticeLevel::Error, message);
                        } else if let Some(slot) = self.parked.iter_mut()
                            .find(|slot| slot.id == session_id)
                        {
                            slot.transcript.push_notice(NoticeLevel::Error, message);
                        }
                    }
                    CtlEvent::ModelSwitchFailed {
                        session_id,
                        model,
                        effort,
                        message,
                    } => {
                        // The agent rejected a switch the UI had already shown
                        // optimistically: revert that value in the owning tab
                        // and surface the error instead of leaving a lie.
                        if session_id == self.session_id {
                            if let Some(model) = &model {
                                if self.selected_model.as_deref() == Some(model.as_str()) {
                                    self.selected_model = None;
                                }
                            }
                            if let Some(effort) = &effort {
                                if self.modes.effort.as_deref() == Some(effort.as_str()) {
                                    self.modes.effort = None;
                                }
                            }
                            self.transcript.push_notice(NoticeLevel::Error, message);
                        } else if let Some(slot) = self.parked.iter_mut()
                            .find(|slot| slot.id == session_id)
                        {
                            if let Some(model) = &model {
                                if slot.selected_model.as_deref() == Some(model.as_str()) {
                                    slot.selected_model = None;
                                }
                            }
                            if let Some(effort) = &effort {
                                if slot.modes.effort.as_deref() == Some(effort.as_str()) {
                                    slot.modes.effort = None;
                                }
                            }
                            slot.transcript.push_notice(NoticeLevel::Error, message);
                        }
                        self.needs_redraw = true;
                    }
                    CtlEvent::SessionError {
                        session_id,
                        message,
                    } => {
                        // A failure for one specific session (prompt,
                        // steer, config select, …): the notice lands in that
                        // session's own transcript — a parked tab must not
                        // spill errors onto the viewed one. The session's
                        // delivery state settles (its prompt, if any, is not
                        // coming back) but its queue is left alone: an
                        // unbound/forgotten tab must not burn queued
                        // prompts through repeated rejections.
                        if session_id == self.session_id {
                            self.prompt_pending = false;
                            self.state = RunState::Idle;
                            self.run_started = None;
                            self.transcript
                                .push_notice(NoticeLevel::Error, message);
                        } else if let Some(slot) = self
                            .parked
                            .iter_mut()
                            .find(|slot| slot.id == session_id)
                        {
                            slot.prompt_pending = false;
                            slot.running = false;
                            slot.transcript
                                .push_notice(NoticeLevel::Error, message);
                        }
                    }
                    CtlEvent::BindFailed { message } => {
                        // session/new·resume failed outright. acp completes
                        // bind requests in order, so the FIFO head owns the
                        // failure: drop its entry so a later bind cannot
                        // land on the dead request, and tell the tab that
                        // asked (it stays open and unbound — /close or
                        // retry /new·resume).
                        if let Some(awaiting) = self.awaiting_binds.pop_front() {
                            if awaiting.open {
                                let msg = self.locale.trf(
                                    "session bind failed: {} — this tab stays open; /close it or retry /new",
                                    "会话绑定失败：{} —— 本标签页保持打开；/close 关闭或重试 /new",
                                    &[message.clone()],
                                );
                                if self.session_id == awaiting.id {
                                    self.transcript.push_notice(NoticeLevel::Warn, msg);
                                } else if let Some(slot) = self
                                    .parked
                                    .iter_mut()
                                    .find(|slot| slot.id == awaiting.id)
                                {
                                    slot.transcript.push_notice(NoticeLevel::Warn, msg);
                                }
                            }
                        }
                        self.show_tip(self.locale.trf(
                            "session bind failed: {}",
                            "会话绑定失败：{}",
                            &[message],
                        ));
                        self.needs_redraw = true;
                    }
                    CtlEvent::CancelRequested { session_id } => {
                        if session_id == self.session_id {
                            self.state_note = "cancelling".into();
                            self.transcript.cancel_open_work();
                        } else if let Some(slot) =
                            self.parked.iter_mut().find(|slot| slot.id == session_id)
                        {
                            slot.state_note = "cancelling".into();
                            slot.transcript.cancel_open_work();
                        }
                    }
                    CtlEvent::Interrupted { session_id } => {
                        // One connection can run turns for several sessions;
                        // settle whichever session the interruption names —
                        // the viewed one, or a parked slot.
                        if session_id == self.session_id {
                            self.prompt_pending = false;
                            self.state = RunState::Idle;
                            self.run_started = None;
                            self.state_note.clear();
                            self.transcript.cancel_open_work();
                            self.transcript
                                .push_notice(
                                    NoticeLevel::Warn,
                                    self.locale
                                        .tr("interrupted — turn cancelled", "已中断 —— 本轮已取消")
                                        .into(),
                                );
                        } else if let Some(slot) =
                            self.parked.iter_mut().find(|slot| slot.id == session_id)
                        {
                            slot.prompt_pending = false;
                            slot.running = false;
                            slot.transcript.cancel_open_work();
                            slot.transcript
                                .push_notice(
                                    NoticeLevel::Warn,
                                    self.locale
                                        .tr("interrupted — turn cancelled", "已中断 —— 本轮已取消")
                                        .into(),
                                );
                        }
                        self.dispatch_session_queue(&session_id, ctl);
                    }
                    CtlEvent::Skills { session_id, skills } => {
                        let is_live = session_id
                            .as_deref()
                            .is_none_or(|session_id| session_id == self.session_id);
                        if is_live {
                            self.skills = skills;
                        } else if let Some(session_id) = session_id.as_deref() {
                            if let Some(slot) =
                                self.parked.iter_mut().find(|slot| slot.id == session_id)
                            {
                                slot.skills = skills;
                            }
                        }
                    }
                    CtlEvent::StaticPlugins { plugins } => {
                        self.static_plugins = plugins;
                        self.open_plugin_tree();
                    }
                    CtlEvent::CordisPlugins { plugins } => {
                        self.cordis_plugins = plugins;
                        self.open_cordis_plugin_picker();
                    }
                    CtlEvent::Catalog {
                        session_id: Some(session_id),
                        models,
                        presets,
                    } if session_id != self.session_id => {
                        if let Some(slot) =
                            self.parked.iter_mut().find(|slot| slot.id == session_id)
                        {
                            if !presets.is_empty() {
                                slot.presets = presets;
                            }
                            if !models.is_empty() {
                                slot.models = models;
                            }
                        }
                    }
                    CtlEvent::Catalog { models, presets, .. } => {
                        if !presets.is_empty() {
                            self.last_presets = presets.clone();
                        }
                        if !models.is_empty() {
                            self.last_models = models.clone();
                        }
                        let mode_current = self.current_mode();
                        let model_current = self.current_model();
                        let model_provider = self.cfg.provider.clone();
                        if let Some(picker) = &mut self.picker {
                            match picker.kind {
                                PickerKind::Model if !models.is_empty() => {
                                    picker.items = models
                                        .into_iter()
                                        .map(|m| PickerItem {
                                            id: m.id.clone(),
                                            label: m.id,
                                            meta: format!(
                                                "{} · {}{}",
                                                m.provider,
                                                m.name,
                                                if m.vision { " · vision" } else { "" }
                                            ),
                                            provider: Some(m.provider),
                                        })
                                        .collect();
                                    picker.sel = picker
                                        .items
                                        .iter()
                                        .position(|i| {
                                            i.id == model_current
                                                && i.provider.as_deref()
                                                    == Some(model_provider.as_str())
                                        })
                                        // Same id under an unknown provider
                                        // still beats pinning row 0.
                                        .or_else(|| {
                                            picker
                                                .items
                                                .iter()
                                                .position(|i| i.id == model_current)
                                        })
                                        .unwrap_or(0);
                                }
                                PickerKind::Mode if !presets.is_empty() => {
                                    picker.items = presets
                                        .into_iter()
                                        .map(|p| PickerItem {
                                            id: p.id.clone(),
                                            label: p.name,
                                            meta: if p.broken {
                                                format!("⚠ broken · {}", p.description)
                                            } else {
                                                p.description
                                            },
                                            provider: None,
                                        })
                                        .collect();
                                    picker.sel = picker
                                        .items
                                        .iter()
                                        .position(|i| i.id == mode_current)
                                        .unwrap_or(0);
                                }
                                _ => {}
                            }
                        }
                    }
                    CtlEvent::SessionModes {
                        session_id,
                        modes,
                        current,
                    } => {
                        let is_live = match &session_id {
                            Some(sid) => sid == &self.session_id,
                            None => true,
                        };
                        if is_live {
                            if !modes.is_empty() {
                                self.permission_choices = modes.clone();
                            }
                            if let Some(id) = &current {
                                self.modes.permission = Some(id.clone());
                            }
                            let reported = self.modes.permission.clone();
                            let current_id = self.current_permission().to_string();
                            let choices = self.permission_choices.clone();
                            if let Some(picker) = &mut self.picker {
                                if matches!(picker.kind, PickerKind::Permission) && !choices.is_empty()
                                {
                                    picker.items = permission_picker_items(
                                        &choices,
                                        reported.as_deref(),
                                        &current_id,
                                    );
                                    picker.sel = picker
                                        .items
                                        .iter()
                                        .position(|i| i.id == current_id)
                                        .unwrap_or(0);
                                }
                            }
                        } else if let Some(sid) = session_id.as_deref() {
                            if let Some(slot) = self.parked.iter_mut().find(|s| s.id == sid) {
                                if !modes.is_empty() {
                                    slot.permission_choices = modes;
                                }
                                if let Some(id) = current {
                                    slot.modes.permission = Some(id);
                                }
                            }
                        }
                    }
                    CtlEvent::Efforts {
                        session_id,
                        efforts,
                        default,
                    } => {
                        let is_live = session_id
                            .as_deref()
                            .is_none_or(|session_id| session_id == self.session_id);
                        if is_live {
                            if !efforts.is_empty() {
                                self.effort_choices = efforts.clone();
                            }
                            self.open_effort_picker(efforts, default);
                        } else if let Some(session_id) = session_id.as_deref() {
                            if let Some(slot) =
                                self.parked.iter_mut().find(|slot| slot.id == session_id)
                            {
                                if !efforts.is_empty() {
                                    slot.effort_choices = efforts;
                                }
                            }
                        }
                    }
                    CtlEvent::PresetSet {
                        session_id,
                        preset,
                    } => {
                        let is_live = session_id.is_empty() || session_id == self.session_id;
                        let label = self.agent_label(&preset);
                        if is_live {
                            self.modes.agent_preset = Some(preset.clone());
                            self.transcript.push_notice(
                                NoticeLevel::Info,
                                self.locale.trf(
                                    "⚙ agent → {} · composes on this session's first prompt",
                                    "⚙ Agent → {} · 在本会话首次输入时生效",
                                    &[label],
                                ),
                            );
                        } else if let Some(slot) =
                            self.parked.iter_mut().find(|s| s.id == session_id)
                        {
                            slot.modes.agent_preset = Some(preset.clone());
                            slot.transcript.push_notice(
                                NoticeLevel::Info,
                                self.locale.trf(
                                    "⚙ agent → {} · composes on this session's first prompt",
                                    "⚙ Agent → {} · 在本会话首次输入时生效",
                                    &[label],
                                ),
                            );
                        }
                    }
                    CtlEvent::TuiOpDone(desc) => {
                        if self.show_banner {
                            self.show_tip(desc);
                        } else {
                            self.transcript.push_notice(NoticeLevel::Info, desc);
                        }
                    }
                    CtlEvent::TuiOpFailed(desc) => {
                        self.transcript.push_notice(NoticeLevel::Warn, desc);
                    }
                    CtlEvent::SessionAuth { session_id, snapshot, open } => {
                        if session_id == self.session_id {
                            self.handle_inner(AppEvent::Ctl(CtlEvent::Auth(snapshot)), ctl);
                            if open { self.open_auth_surface(ctl); }
                        } else if let Some(slot) = self.parked.iter_mut().find(|slot| slot.id == session_id) {
                            if let Some(connection) = &mut slot.connection { connection.auth = snapshot; }
                        }
                    }
                    CtlEvent::Auth(snap) => {
                        let retrying_prompt =
                            self.state == RunState::Running || self.prompt_pending;
                        if let Some((level, text)) = snap.notice(self.locale) {
                            self.transcript.push_notice(level, text);
                        }
                        if snap.status == crate::acp_auth::AuthStatus::Configured {
                            if self.view_overlay.as_ref().is_some_and(|view| view.id == "builtin.auth.failure") {
                                self.view_overlay = None;
                            }
                            if matches!(
                                self.picker.as_ref().map(|p| p.kind),
                                Some(PickerKind::Auth)
                            ) {
                                self.picker = None;
                            }
                        }
                        if matches!(snap.status, crate::acp_auth::AuthStatus::NeedsAuth | crate::acp_auth::AuthStatus::Failed) {
                            self.prompt_pending = retrying_prompt;
                            self.state = RunState::Idle;
                            self.run_started = None;
                            self.state_note.clear();
                        }
                        if snap.status == crate::acp_auth::AuthStatus::Failed {
                            self.open_text_overlay("builtin.auth.failure",
                                self.locale.tr("Sign-in failed", "登录失败").into(),
                                format!("{}\n\n{}", snap.message.as_deref().unwrap_or("ACP authenticate failed"),
                                    self.locale.tr("Close this panel, then use /auth to retry or choose another method. Browser authorization alone does not mean the Agent accepted sign-in.",
                                        "关闭面板后可用 /auth 重试或选择其他方式。浏览器授权完成不代表 Agent 已接受登录。")));
                        }
                        self.auth = snap;
                    }
                    CtlEvent::OpenAuth => {
                        self.open_auth_surface(ctl);
                    }
                    CtlEvent::AgentCaps {
                        load_session,
                        list_session,
                        resume_session,
                    } => {
                        self.load_session = load_session;
                        self.list_session = list_session;
                        self.resume_session_cap = resume_session;
                    }
                    CtlEvent::SessionBound { session_id, notice } => {
                        self.connection_error = None;
                        // The session that just bound, for the queue dispatch
                        // below (prompts submitted while the tab was unbound
                        // are held in its queue — acp.rs rejects unbound ids).
                        let mut just_bound: Option<String> = None;
                        if !self.startup_bound && !self.awaiting_binds.is_empty() {
                            // The unrequested startup/reconnect session/new
                            // resolved while the user's own /new·resume is
                            // still in flight — acp completes the startup
                            // bind before any UI request, so this bind owns
                            // no awaiting entry. Its tab is the parked
                            // session that is unbound and not itself
                            // awaiting anything; never steal the FIFO head
                            // from the request that really owns it.
                            self.startup_bound = true;
                            let owner = self.parked.iter().position(|slot| {
                                !slot.session_bound
                                    && !self.awaiting_binds.iter().any(|e| e.id == slot.id)
                            });
                            match owner {
                                Some(pidx) => {
                                    let slot = &mut self.parked[pidx];
                                    let old_id = slot.id.clone();
                                    slot.id = session_id.clone();
                                    slot.transcript.set_root_session(session_id.clone());
                                    slot.session_bound = true;
                                    if let Some(notice) = notice {
                                        slot.transcript
                                            .push_notice(NoticeLevel::Info, notice);
                                    }
                                    for (_, sid, _, _) in &mut self.shell_pending {
                                        if sid == &old_id {
                                            *sid = session_id.clone();
                                        }
                                    }
                                    just_bound = Some(slot.id.clone());
                                }
                                None => {
                                    if !self.session_bound
                                        && !self.awaiting_binds.iter().any(|e| e.id == self.session_id)
                                    {
                                        if self.session_id != session_id {
                                            self.reset_subagent_views();
                                self.session_model = None;
                                        }
                                        let old_id = self.session_id.clone();
                                        self.session_id = session_id.clone();
                                        self.transcript.set_root_session(session_id.clone());
                                        self.session_bound = true;
                                        if let Some(notice) = notice {
                                            self.transcript
                                                .push_notice(NoticeLevel::Info, notice);
                                        }
                                        for (_, sid, _, _) in &mut self.shell_pending {
                                            if sid == &old_id {
                                                *sid = session_id.clone();
                                            }
                                        }
                                        just_bound = Some(self.session_id.clone());
                                    } else {
                                        // The viewed tab is bound or awaiting its own bind:
                                        // park this startup session as a fresh slot.
                                        let mut slot =
                                            SessionSlot::fresh(session_id.clone(), true);
                                        slot.transcript.locale = self.locale;
                                        if let Some(notice) = notice {
                                            slot.transcript.push_notice(NoticeLevel::Info, notice);
                                        }
                                        just_bound = Some(session_id.clone());
                                        self.parked.push(slot);
                                    }
                                }
                            }
                        } else if let Some(awaiting) = self.awaiting_binds.pop_front() {
                            // The tab that asked for session/new (placeholder
                            // id) or session/resume·load (target id) owns
                            // this bind — the user may have switched away
                            // while it resolved, so rebind by the awaiting
                            // id, not by which tab happens to be live.
                            if !awaiting.open {
                                // The requesting tab was closed (/close)
                                // before the bind resolved. acp already
                                // registered the new session server-side, so
                                // forget it and never hijack the viewed tab.
                                ctl.send(Cmd::ForgetSession {
                                    session_id: session_id.clone(),
                                });
                                self.show_tip(self.locale.trf(
                                    "session {} bound after its tab was closed",
                                    "会话 {} 已绑定，但对应标签页已被关闭",
                                    &[session_id.clone()],
                                ));
                            } else if self.session_id == awaiting.id {
                                let old_id = self.session_id.clone();
                                self.session_id = session_id.clone();
                                self.transcript.set_root_session(session_id.clone());
                                self.session_bound = true;
                                if let Some(notice) = notice {
                                    self.transcript.push_notice(NoticeLevel::Info, notice);
                                }
                                for (_, sid, _, _) in &mut self.shell_pending {
                                    if sid == &old_id || sid == &awaiting.id {
                                        *sid = session_id.clone();
                                    }
                                }
                                just_bound = Some(self.session_id.clone());
                            } else if let Some(slot) =
                                self.parked.iter_mut().find(|slot| slot.id == awaiting.id)
                            {
                                let old_id = slot.id.clone();
                                slot.id = session_id.clone();
                                slot.transcript.set_root_session(session_id.clone());
                                slot.session_bound = true;
                                if let Some(notice) = notice {
                                    slot.transcript.push_notice(NoticeLevel::Info, notice);
                                }
                                for (_, sid, _, _) in &mut self.shell_pending {
                                    if sid == &old_id || sid == &awaiting.id {
                                        *sid = session_id.clone();
                                    }
                                }
                                just_bound = Some(slot.id.clone());
                            } else {
                                self.show_tip(self.locale.trf(
                                    "session {} bound after its tab was closed",
                                    "会话 {} 已绑定，但对应标签页已被关闭",
                                    &[session_id.clone()],
                                ));
                            }
                        } else if let Some(slot) =
                            self.parked.iter_mut().find(|slot| slot.id == session_id)
                        {
                            // A session/load for a parked tab resolved.
                            slot.session_bound = true;
                            if let Some(notice) = notice {
                                slot.transcript.push_notice(NoticeLevel::Info, notice);
                            }
                            just_bound = Some(slot.id.clone());
                        } else {
                            // Startup / reconnect: rebind the viewed session.
                            self.startup_bound = true;
                            if self.session_id != session_id {
                                self.reset_subagent_views();
                                self.session_model = None;
                            }
                            let old_id = self.session_id.clone();
                            self.session_id = session_id.clone();
                            self.transcript.set_root_session(session_id.clone());
                            self.session_bound = true;
                            if let Some(notice) = notice {
                                self.transcript.push_notice(NoticeLevel::Info, notice);
                            }
                            for (_, sid, _, _) in &mut self.shell_pending {
                                if sid == &old_id {
                                    *sid = session_id.clone();
                                }
                            }
                            just_bound = Some(self.session_id.clone());
                        }
                        if let Some(bound) = just_bound {
                            // A `--session-id` start binds with a notice worth
                            // reading — resumed, ignored, or failed — and a
                            // resume has no transcript of its own; the welcome
                            // banner would cover all of it. One-shot: only the
                            // first bind after the flag dismisses it.
                            if self.cfg.startup_session.take().is_some() {
                                self.show_banner = false;
                            }
                            self.dispatch_session_queue(&bound, ctl);
                            ctl.send(Cmd::FetchSkills { session_id: bound });
                        }
                        // `--model` is an explicit "use THIS model for this
                        // run": apply it to whichever session the startup bind
                        // landed on. Once — the bind clears `session_model`, so
                        // there is nothing to compare against yet, and a later
                        // /new or /resume keeps whatever that agent reports.
                        if let Some(model) = self.startup_model.take() {
                            self.selected_model = Some(model.clone());
                            ctl.send(Cmd::SelectModel {
                                session_id: self.session_id.clone(),
                                provider: None,
                                model: Some(model),
                                effort: None,
                            });
                        }
                    }
                    CtlEvent::SessionList {
                        requester_session_id,
                        sessions,
                        prefix,
                        limit,
                    } => {
                        self.on_acp_session_list(
                            requester_session_id,
                            sessions,
                            prefix,
                            limit,
                            ctl,
                        );
                    }
                    CtlEvent::SessionListUnavailable {
                        requester_session_id,
                        prefix,
                        limit,
                        error,
                    } => {
                        self.on_acp_session_list_unavailable(
                            requester_session_id,
                            prefix,
                            limit,
                            error,
                            ctl,
                        );
                    }
                }
                self.needs_redraw = true;
            }
            AppEvent::PermissionAsk {
                session_id,
                title,
                options,
                reply,
            } => {
                self.open_permission_ask(&session_id, title, options, reply);
            }
            AppEvent::ElicitationAsk {
                session_id,
                form,
                reply,
            } => {
                self.open_elicitation_ask(session_id.as_deref(), form, reply);
            }
            AppEvent::ShellDone { id, code, output } => {
                if let Some(pos) = self
                    .shell_pending
                    .iter()
                    .position(|(sid, _, _, _)| *sid == id)
                {
                    let (_, session, cell, gen) = self.shell_pending.remove(pos);
                    // The shell is workspace-wide but its cell lives in the
                    // transcript of the session that ran it — the user may
                    // have switched tabs while the command ran. The gen
                    // guard drops results for cells a /clear removed.
                    if session == self.session_id {
                        self.transcript.finish_shell(cell, code, output, gen);
                    } else if let Some(slot) =
                        self.parked.iter_mut().find(|slot| slot.id == session)
                    {
                        slot.transcript.finish_shell(cell, code, output, gen);
                    }
                    self.needs_redraw = true;
                }
                // `!git checkout …` in the session shell moves the branch —
                // refresh the composer cap label right away.
                self.refresh_git_branch(true);
            }
        }
    }

    /// Fold one decoded protocol fact into both client chrome and transcript.
    /// Direct ACP facts and JSON-RPC notifications must take the same path.
    pub(crate) fn apply_ui(&mut self, ui: crate::events::UiEvent) {
        use crate::events::UiEvent as E;

        if let E::TurnStart { session, .. } = &ui {
            if session == &self.session_id {
                self.next_subagent_starts_batch = true;
            }
        }

        if let E::SubagentStarted { parent, child } = &ui {
            if parent != &self.session_id && !self.subagents.iter().any(|view| view.id == *parent)
            {
                // A parked session's subagent tree: register the child in
                // its slot and fold the event into the slot's transcripts.
                for slot in &mut self.parked {
                    if slot.id == *parent || slot.subagents.iter().any(|v| v.id == *parent) {
                        // A fresh turn starts a new batch, exactly like the
                        // live path below — background sessions must keep
                        // their current/history grouping current.
                        if slot.next_subagent_starts_batch {
                            slot.current_subagents.clear();
                            slot.next_subagent_starts_batch = false;
                        }
                        slot.current_subagents.insert(child.clone());
                        upsert_subagent_view(&mut slot.subagents, parent, child, self.locale);
                        if slot.id == *parent {
                            slot.transcript.apply(ui);
                        } else if let Some(view) =
                            slot.subagents.iter_mut().find(|view| view.id == *parent)
                        {
                            view.transcript.apply(ui);
                        }
                        self.needs_redraw = true;
                        return;
                    }
                }
                // Unknown parent: a session this client never opened (or
                // already closed) — drop it, never leak it into live state.
                return;
            }
            if self.next_subagent_starts_batch {
                self.current_subagents.clear();
                self.next_subagent_starts_batch = false;
            }
            self.current_subagents.insert(child.clone());
            upsert_subagent_view(&mut self.subagents, parent, child, self.locale);
            if parent == &self.session_id {
                self.transcript.apply(ui);
            } else if let Some(view) = self.subagents.iter_mut().find(|view| view.id == *parent) {
                view.transcript.apply(ui);
            }
            self.needs_redraw = true;
            return;
        }

        if let E::SubagentFinished { child, failed } = &ui {
            if !self.subagents.iter().any(|view| view.id == *child) {
                // A parked session's subagent: settle it inside its slot.
                for slot in &mut self.parked {
                    if let Some(view) = slot.subagents.iter_mut().find(|view| view.id == *child) {
                        view.running = false;
                        view.failed = *failed;
                        let parent = view.parent.clone();
                        if parent == slot.id {
                            slot.transcript.apply(ui);
                        } else if let Some(pview) =
                            slot.subagents.iter_mut().find(|view| view.id == parent)
                        {
                            pview.transcript.apply(ui);
                        }
                        // Issue #80 parity: a parked session's rail also
                        // auto-closes once every subagent task has ended.
                        if slot.agent_selection.is_some()
                            && !slot.subagents.iter().any(|view| view.running || view.failed)
                        {
                            slot.agent_selection = None;
                        }
                        self.needs_redraw = true;
                        return;
                    }
                }
                // Unknown child — drop (same guard as SubagentStarted).
                return;
            }
            let parent = self
                .subagents
                .iter_mut()
                .find(|view| view.id == *child)
                .map(|view| {
                    view.running = false;
                    view.failed = *failed;
                    view.parent.clone()
                });
            if parent.as_deref() == Some(self.session_id.as_str()) {
                self.transcript.apply(ui);
            } else if let Some(parent) = parent {
                if let Some(view) = self.subagents.iter_mut().find(|view| view.id == parent) {
                    view.transcript.apply(ui);
                }
            }
            // Issue #80: the panel auto-closes once every subagent task has
            // ended. An inline selection left open after the last task would
            // otherwise keep the rail visible forever — the Client plugin
            // only hides the summary while nothing is selected.
            if self.agent_selection.is_some()
                && !self.subagents.iter().any(|view| view.running || view.failed)
            {
                self.agent_selection = None;
            }
            self.needs_redraw = true;
            return;
        }

        if let Some(session) = ui_session(&ui) {
            if session != self.session_id {
                if let Some(view) = self.subagents.iter_mut().find(|view| view.id == session) {
                    let visible = self.active_subagent.as_deref() == Some(session);
                    view.transcript.apply(ui);
                    // Hidden child output only changes its own transcript.
                    // Lifecycle events above still redraw the Agents dock;
                    // tick drives its running animation independently.
                    self.needs_redraw |= visible;
                    return;
                }
                for slot in &mut self.parked {
                    if slot.id == session {
                        Self::apply_to_slot(slot, ui);
                        self.needs_redraw = true;
                        return;
                    }
                    if let Some(view) = slot.subagents.iter_mut().find(|view| view.id == session) {
                        view.transcript.apply(ui);
                        return;
                    }
                }
                // A session this client never opened (or already closed):
                // drop the event. Foreign-session facts must never fall
                // through into the live transcript (issue #94 leak guard).
                return;
            }
        }

        let mut apply_to_transcript = true;
        match &ui {
            E::PlanMode { session, active } if *session == self.session_id => {
                if self.modes.plan == *active {
                    apply_to_transcript = false;
                } else {
                    self.modes.plan = *active;
                }
            }
            E::SandboxMode { session, mode } if *session == self.session_id => {
                self.modes.sandbox = Some(mode.clone());
            }
            E::ApprovalPolicy { session, policy } if *session == self.session_id => {
                self.modes.approval = Some(policy.clone());
            }
            E::PermissionPreset { session, preset } if *session == self.session_id => {
                self.modes.permission = Some(preset.clone());
            }
            E::AgentPreset { session, preset } if *session == self.session_id => {
                self.modes.agent_preset = Some(preset.clone());
                apply_to_transcript = false;
            }
            E::ReasoningEffort { session, effort } if *session == self.session_id => {
                self.modes.effort = Some(effort.clone());
                apply_to_transcript = false;
            }
            E::SessionTitle { session, title } if *session == self.session_id => {
                self.session_title = Some(title.clone());
            }
            E::SessionModel { session, model } if *session == self.session_id => {
                self.session_model = Some(model.clone());
                apply_to_transcript = false;
            }
            _ => {}
        }

        if let E::SessionStatus { session, running } = &ui {
            if *session == self.session_id {
                self.state = if *running {
                    RunState::Running
                } else {
                    RunState::Idle
                };
                if *running {
                    if self.run_started.is_none() {
                        self.run_started = Some(Instant::now());
                    }
                } else {
                    self.prompt_pending = false;
                    self.run_started = None;
                    self.state_note.clear();
                }
            }
        }
        if apply_to_transcript {
            self.transcript.apply(ui);
        }
        self.needs_redraw = true;
    }

    pub(crate) fn handle_term(&mut self, ev: Event, ctl: &Controller) {
        match ev {
            Event::Key(key) if key.kind != KeyEventKind::Release => {
                // CG rescue first: a bare arrow/⌫ with ⌘/⌥ physically held
                // gets its modifier restored (macOS terminals drop them).
                self.handle_key(crate::input::rescue_key(key), ctl)
            }
            Event::Mouse(mouse) => self.handle_mouse(mouse, ctl),
            Event::Resize(..) => self.needs_redraw = true,
            Event::Paste(text) => {
                if let Some(keys) = decode_leaked_csi_u_keys(&text) {
                    for key in keys {
                        if key.kind != KeyEventKind::Release {
                            self.handle_key(crate::input::rescue_key(key), ctl);
                        }
                    }
                    return;
                }
                if let Some(ask) = &mut self.elicitation_ask {
                    ask.form.paste(&text);
                    self.needs_redraw = true;
                    return;
                }
                if let Some(select) = &mut self.select_overlay {
                    if select.searchable {
                        select.query.extend(text.chars().filter(|ch| !ch.is_control())
                            .take(256_usize.saturating_sub(select.query.chars().count())));
                        select.reconcile_search();
                        self.needs_redraw = true;
                    }
                    return;
                }
                self.slash_completion_dismissed = false;
                // The composer is multi-line (soft wrap, ctrl+j), so pasted
                // text keeps its line structure instead of being flattened
                // to spaces (issue #54). `TextArea::insert_str` understands
                // both `\n` and `\r\n`; normalize stray CR-only line
                // endings some terminals (iTerm2 et al.) send.
                let text = text.replace("\r\n", "\n").replace('\r', "\n");
                self.input.insert_str(&text);
                self.input_sel = None;
                self.reconcile_attachments();
                self.needs_redraw = true;
            }
            _ => {}
        }
    }

    /// Cancel compositor-owned modals before a session switch, mirroring
    /// the Esc paths of `handle_view_key` / `handle_select_key` /
    /// `handle_slider_key` so the plugin releases its single-overlay slot
    /// (its `current` clears and future overlay opens work again).
    /// Painter-owned views (`notify_plugin == false`, i.e. `/help`, `/keys`,
    /// `/session`, painter `/status`) are left alone — they park with their
    /// session inside the switch and resurface on return.
    pub(crate) fn cancel_plugin_overlays(&mut self, ctl: &Controller) {
        if let Some(view) = self.view_overlay.take() {
            if view.notify_plugin {
                ctl.send(Cmd::PluginOverlayEvent {
                    id: view.id,
                    event: "cancel".into(),
                    value: None,
                });
            } else {
                self.view_overlay = Some(view);
            }
        }
        if let Some(slider) = self.slider_overlay.take() {
            ctl.send(Cmd::PluginOverlayEvent {
                id: slider.id,
                event: "cancel".into(),
                value: Some(serde_json::json!(slider.value)),
            });
        }
        if let Some(select) = self.select_overlay.take() {
            let value = select.options[select.sel].value.clone();
            ctl.send(Cmd::PluginOverlayEvent {
                id: select.id,
                event: "cancel".into(),
                value: Some(serde_json::json!(value)),
            });
        }
    }
}

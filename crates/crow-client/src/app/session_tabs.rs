//! session_tabs: App methods for the session_tabs surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crate::bus::Cmd;
use crate::controller::Controller;
use crate::transcript::Transcript;

impl App {
    /// Move the live session's per-session state out of the App fields into
    /// a parking slot, leaving cheap placeholders behind. Always paired with
    /// [`Self::put_live_slot`] before anything reads the fields again.
    pub(crate) fn take_live_slot(&mut self) -> SessionSlot {
        let mut placeholder = Transcript::new(String::new());
        placeholder.locale = self.locale;
        SessionSlot {
            id: std::mem::take(&mut self.session_id),
            connection: Some(crate::bus::SessionConnection {
                server: self.server_info.clone(), auth: self.auth.clone(),
                load_session: self.load_session, list_session: self.list_session,
                resume_session: self.resume_session_cap,
            }),
            title: self.session_title.take(),
            transcript: std::mem::replace(&mut self.transcript, placeholder),
            // Composer + chat chrome bound to the tab (see `put_live_slot`).
            input: std::mem::take(&mut self.input),
            pending_images: std::mem::take(&mut self.pending_images),
            input_expanded: std::mem::take(&mut self.input_expanded),
            file_menu: self.file_menu.take(),
            file_menu_dismissed: self.file_menu_dismissed.take(),
            scroll_up: std::mem::take(&mut self.scroll_up),
            selected_model: std::mem::take(&mut self.selected_model),
            session_model: self.session_model.take(),
            show_banner: std::mem::take(&mut self.show_banner),
            state_note: std::mem::take(&mut self.state_note),
            run_started: self.run_started.take(),
            running: self.state != RunState::Idle || self.prompt_pending,
            completed_unseen: false,
            prompt_queue: std::mem::take(&mut self.prompt_queue),
            queue_selection: self.queue_selection.take(),
            queue_edit: self.queue_edit.take(),
            prompt_pending: std::mem::take(&mut self.prompt_pending),
            modes: std::mem::take(&mut self.modes),
            skills: std::mem::take(&mut self.skills),
            presets: std::mem::take(&mut self.last_presets),
            models: std::mem::take(&mut self.last_models),
            permission_choices: std::mem::take(&mut self.permission_choices),
            effort_choices: std::mem::take(&mut self.effort_choices),
            session_bound: std::mem::take(&mut self.session_bound),
            pending_steer_cells: std::mem::take(&mut self.pending_steer_cells),
            subagents: std::mem::take(&mut self.subagents),
            current_subagents: std::mem::take(&mut self.current_subagents),
            next_subagent_starts_batch: std::mem::replace(&mut self.next_subagent_starts_batch, true),
            active_subagent: self.active_subagent.take(),
            agent_selection: self.agent_selection.take(),
            permission_ask: self.permission_ask.take(),
            elicitation_ask: self.elicitation_ask.take(),
            // Painter info popups ride along with their session; plugin
            // views are filtered out (a compositor overlay must never be
            // resurrected stale on another tab — the tab-click path
            // cancels it before the switch, anything left here is dropped).
            view_overlay: self.view_overlay.take().filter(|view| !view.notify_plugin),
            plugin_tree: self.plugin_tree.take(),
        }
    }

    /// Load a slot's state into the App fields — the inverse of
    /// [`Self::take_live_slot`]. RunState is recomputed from the slot's
    /// authoritative `running` bit; an in-flight turn keeps its elapsed
    /// timer and state note.
    pub(crate) fn put_live_slot(&mut self, slot: SessionSlot) {
        self.session_id = slot.id;
        self.set_session_connection(slot.connection.unwrap_or(crate::bus::SessionConnection {
            server: None,
            auth: crate::acp_auth::AuthSnapshot::none(),
            load_session: false,
            list_session: false,
            resume_session: false,
        }));
        self.session_title = slot.title;
        self.transcript = slot.transcript;
        self.queued = slot.prompt_queue.len();
        self.prompt_queue = slot.prompt_queue;
        self.queue_selection = slot.queue_selection;
        self.queue_edit = slot.queue_edit;
        self.prompt_pending = slot.prompt_pending;
        self.modes = slot.modes;
        self.skills = slot.skills;
        self.last_presets = slot.presets;
        self.last_models = slot.models;
        self.permission_choices = slot.permission_choices;
        self.effort_choices = slot.effort_choices;
        self.session_bound = slot.session_bound;
        self.pending_steer_cells = slot.pending_steer_cells;
        self.subagents = slot.subagents;
        self.current_subagents = slot.current_subagents;
        self.next_subagent_starts_batch = slot.next_subagent_starts_batch;
        self.active_subagent = slot.active_subagent;
        self.agent_selection = slot.agent_selection;
        // A session-bound ask rides along with its session: an ask that was
        // open when the user left this tab (or that arrived while parked)
        // resurfaces here, untouched, ready to answer or Esc away.
        self.permission_ask = slot.permission_ask;
        self.elicitation_ask = slot.elicitation_ask;
        // Painter popups and the /plugins tree resurface the same way.
        self.view_overlay = slot.view_overlay;
        self.plugin_tree = slot.plugin_tree;
        // Composer + chat chrome bound to the tab: draft, staged images,
        // @file browser, scroll, banner, model pick, running note.
        self.input = slot.input;
        self.pending_images = slot.pending_images;
        self.input_expanded = slot.input_expanded;
        self.file_menu = slot.file_menu;
        self.file_menu_dismissed = slot.file_menu_dismissed;
        self.scroll_up = slot.scroll_up;
        self.selected_model = slot.selected_model;
        self.session_model = slot.session_model;
        self.show_banner = slot.show_banner;
        let running = slot.running || slot.prompt_pending;
        self.state = if running {
            RunState::Running
        } else {
            RunState::Idle
        };
        // Restore the meta-row chrome as left: an in-flight turn keeps its
        // elapsed timer and note; a session that settled while parked
        // shows the idle meta row.
        self.run_started = if running { slot.run_started } else { None };
        self.state_note = if running {
            slot.state_note
        } else {
            String::new()
        };
    }

    /// Per-view caches that must not leak across a tab switch. Draft,
    /// staged images, scroll and model pick come back from the slot via
    /// [`Self::put_live_slot`]; everything here is transient interaction
    /// state that must never resurface on the incoming tab.
    pub(crate) fn after_switch(&mut self) {
        self.chat_view = ChatView::default();
        self.sel = None;
        self.selecting = false;
        self.last_click = None;
        self.input_sel = None;
        self.input_selecting = false;
        self.picker = None;
        self.vim.reset_pending();
        // The ↥ jump cursor indexes this session's transcript cells, and
        // the flash must not carry over to another session's view.
        self.prompt_jump_cell = None;
        self.prompt_flash = None;
        self.prompt_flash_lines = None;
        self.needs_redraw = true;
    }

    /// Switch the view to tab `tab` (conceptual index, live spliced in at
    /// `current`): park the live state into its slot, load the target.
    pub fn switch_to_session(&mut self, tab: usize) {
        if tab == self.current || tab > self.parked.len() {
            return;
        }
        let pidx = if tab < self.current { tab } else { tab - 1 };
        let live = self.take_live_slot();
        let mut target = self.parked.remove(pidx);
        target.completed_unseen = false;
        // The parked copy takes the live tab's conceptual position.
        let park_at = if self.current < tab {
            self.current
        } else {
            self.current - 1
        };
        self.parked.insert(park_at, live);
        self.current = tab;
        self.put_live_slot(target);
        self.after_switch();
    }

    /// Leave the viewed session for another tab — the mouse click and the
    /// `/session prev|next` commands take the same path: transient
    /// interactions are dismissed and compositor-owned overlays are
    /// released with their cancel events (the plugin owns a
    /// single-overlay slot; Esc would send the same). Painter popups and
    /// ACP asks park with their session instead and resurface on return.
    pub fn switch_view_to_tab(&mut self, tab: usize, ctl: &Controller) {
        self.sel = None;
        self.selecting = false;
        self.last_click = None;
        self.input_sel = None;
        self.input_selecting = false;
        if tab != self.current {
            self.cancel_plugin_overlays(ctl);
        }
        self.switch_to_session(tab);
    }

    /// Park the live session and open a fresh tab for `id` at the end.
    /// `bound` is true only when the id is already a real session id.
    pub(crate) fn open_new_session(&mut self, id: String, bound: bool) {
        let live = self.take_live_slot();
        self.parked.insert(self.current, live);
        self.current = self.parked.len();
        let mut slot = SessionSlot::fresh(id, bound);
        slot.transcript.locale = self.locale;
        self.put_live_slot(slot);
        self.after_switch();
    }

    /// Conceptual tab index of the session with this id (live or parked).
    pub(crate) fn tab_index_of(&self, id: &str) -> Option<usize> {
        if self.session_id == id {
            return Some(self.current);
        }
        self.parked.iter().position(|slot| slot.id == id).map(|pidx| {
            if pidx < self.current {
                pidx
            } else {
                pidx + 1
            }
        })
    }

    /// Tab strip model: every session in tab order with the live tab
    /// spliced in at `current`. Native status chrome fed by session status
    /// facts (same source as `state_line`, never the palette/slot systems).
    pub fn session_tabs(&self) -> Vec<SessionTab> {
        let mut tabs: Vec<SessionTab> = self
            .parked
            .iter()
            .map(|slot| SessionTab {
                label: slot
                    .title
                    .clone()
                    .filter(|title| !title.trim().is_empty())
                    .unwrap_or_else(|| short_id(&slot.id)),
                running: slot.running || slot.prompt_pending,
                completed_unseen: slot.completed_unseen,
                ask_pending: slot.permission_ask.is_some() || slot.elicitation_ask.is_some(),
                current: false,
            })
            .collect();
        tabs.insert(
            self.current,
            SessionTab {
                label: self
                    .session_title
                    .clone()
                    .filter(|title| !title.trim().is_empty())
                    .unwrap_or_else(|| short_id(&self.session_id)),
                running: self.state != RunState::Idle || self.prompt_pending,
                completed_unseen: false,
                ask_pending: self.permission_ask.is_some() || self.elicitation_ask.is_some(),
                current: true,
            },
        );
        tabs
    }

    /// Number of session tabs (parked + live).
    pub fn session_tab_count(&self) -> usize {
        self.parked.len() + 1
    }

    /// Tab index of the live session — the position where `session_tabs`
    /// splices it into the parked list. The painter uses it to keep the
    /// strip's scroll window anchored on the tab being viewed.
    pub(crate) fn live_tab_index(&self) -> usize {
        self.current
    }

    /// Hit-test a screen cell against the tab rects recorded by the painter.
    pub(crate) fn tab_at(&self, col: u16, row: u16) -> Option<usize> {
        self.tab_rects
            .iter()
            .find(|(rect, _)| {
                col >= rect.x && col < rect.right() && row >= rect.y && row < rect.bottom()
            })
            .map(|(_, idx)| *idx)
    }

    /// Was this session mid-turn (live RunState, or a parked slot's running
    /// bit)? Read just before folding a `SessionStatus` event.
    pub(crate) fn session_was_running(&self, session: &str) -> bool {
        if session == self.session_id {
            matches!(self.state, RunState::Running)
        } else {
            self.parked
                .iter()
                .any(|slot| slot.id == session && slot.running)
        }
    }

    /// Fold an event addressed to a parked session into its slot: the same
    /// mode/status facts the live path folds, plus the running → idle edge
    /// that raises the tab's completion badge. Live UI state is untouched.
    pub(crate) fn apply_to_slot(slot: &mut SessionSlot, ui: crate::events::UiEvent) {
        use crate::events::UiEvent as E;
        let mut apply_to_transcript = true;
        match &ui {
            E::PlanMode { active, .. } => {
                if slot.modes.plan == *active {
                    apply_to_transcript = false;
                } else {
                    slot.modes.plan = *active;
                }
            }
            E::SandboxMode { mode, .. } => slot.modes.sandbox = Some(mode.clone()),
            E::ApprovalPolicy { policy, .. } => slot.modes.approval = Some(policy.clone()),
            E::PermissionPreset { preset, .. } => slot.modes.permission = Some(preset.clone()),
            E::AgentPreset { preset, .. } => {
                slot.modes.agent_preset = Some(preset.clone());
                apply_to_transcript = false;
            }
            E::ReasoningEffort { effort, .. } => {
                slot.modes.effort = Some(effort.clone());
                apply_to_transcript = false;
            }
            E::SessionTitle { title, .. } => slot.title = Some(title.clone()),
            E::SessionModel { model, .. } => {
                slot.session_model = Some(model.clone());
                apply_to_transcript = false;
            }
            _ => {}
        }
        match &ui {
            E::SessionStatus { running, .. } => {
                if slot.running && !running {
                    slot.completed_unseen = true;
                }
                slot.running = *running;
                if !running {
                    slot.prompt_pending = false;
                }
            }
            E::TurnStart { .. } => {
                // A new turn on this session starts a fresh subagent batch
                // (mirror of the live path in `apply_ui`).
                slot.next_subagent_starts_batch = true;
                slot.running = true;
            }
            E::TurnEnd { .. } => {
                if slot.running {
                    slot.completed_unseen = true;
                }
                slot.prompt_pending = false;
            }
            _ => {}
        }
        if apply_to_transcript {
            slot.transcript.apply(ui);
        }
    }

    /// Dispatch the head of one session's queue — the live session takes
    /// the existing path; a parked session echoes into its own transcript
    /// and sends addressed by its own id (acp.rs fans in per session).
    pub(crate) fn dispatch_session_queue(&mut self, session: &str, ctl: &Controller) {
        if session == self.session_id {
            self.dispatch_next_queued(ctl);
            return;
        }
        let Some(slot) = self.parked.iter_mut().find(|slot| slot.id == session) else {
            return;
        };
        if slot.queue_selection.is_some() || slot.queue_edit.is_some() {
            return;
        }
        if !slot.session_bound {
            // Mirror of the live path's guard (dispatch_next_queued): an
            // unbound placeholder must never burn its queue — the prompts
            // would be addressed to an id acp.rs does not know.
            return;
        }
        let Some(prompt) = slot.prompt_queue.pop_front() else {
            return;
        };
        for block in &prompt.blocks {
            match block {
                StagedBlock::Text(text) => slot.transcript.push_user(text.clone(), false),
                StagedBlock::Image(att) => slot.transcript.push_image(
                    att.name.clone(),
                    String::new(),
                    att.path.clone(),
                    att.data.clone(),
                    false,
                ),
            }
        }
        slot.prompt_pending = true;
        slot.running = true;
        slot.run_started = Some(Instant::now());
        slot.state_note = self.locale.tr("sending queued followup", "正在发送排队消息").into();
        slot.scroll_up = 0;
        match prompt.blocks.as_slice() {
            [StagedBlock::Text(text)] => ctl.send(Cmd::Prompt {
                session_id: session.to_string(),
                text: text.clone(),
            }),
            _ => ctl.send(Cmd::PromptImages {
                session_id: session.to_string(),
                blocks: prompt_blocks_from_staged(prompt.blocks),
            }),
        }
    }

    /// Settle one Send Now (steer) outcome. The steer's session may have
    /// been parked or even closed while the agent decided, so the pending
    /// entry is looked up on the viewed tab first and then in every parked
    /// slot (`next_prompt_id` is a single counter, so ids are unique app-
    /// wide). A deferred steer is requeued into its own session's FIFO and
    /// its echo bubble hidden there.
    pub(crate) fn settle_steer(&mut self, message_id: u64, deferred: bool) {
        if let Some(pending) = self.pending_steer_cells.remove(&message_id) {
            if deferred {
                self.transcript.hide_cells(&pending.cells, pending.gen);
                let queued = ClientQueuedPrompt {
                    id: message_id,
                    blocks: pending.blocks,
                };
                if pending.requeue_front {
                    self.prompt_queue.push_front(queued);
                } else {
                    self.prompt_queue.push_back(queued);
                }
                self.queued = self.prompt_queue.len();
                self.show_tip(self.locale.tr(
                    "agent deferred Send Now — queued after the active turn",
                    "Agent 暂缓了立即发送 —— 已排在当前轮次之后",
                ));
            }
            return;
        }
        // The owning tab is not the one in view — settle inside its slot.
        for slot in &mut self.parked {
            if let Some(pending) = slot.pending_steer_cells.remove(&message_id) {
                if deferred {
                    slot.transcript.hide_cells(&pending.cells, pending.gen);
                    let queued = ClientQueuedPrompt {
                        id: message_id,
                        blocks: pending.blocks,
                    };
                    if pending.requeue_front {
                        slot.prompt_queue.push_front(queued);
                    } else {
                        slot.prompt_queue.push_back(queued);
                    }
                }
                return;
            }
        }
        // The session was closed before the settle: nothing to do.
    }
}

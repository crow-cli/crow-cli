//! keys_router: App methods for the keys_router surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::bus::{Cmd, PermissionAskReply};
use crate::controller::Controller;
use crate::input::Action;

impl App {
    pub fn scroll_by(&mut self, delta: i64) {
        // usize::MAX is the JumpTop sentinel — resolve it against the last
        // rendered frame before arithmetic (MAX as i64 wraps to -1, so a
        // wheel flick in the same event burst as JumpTop would teleport the
        // viewport from the top of scrollback to just above the tail).
        let cur = if self.scroll_up == usize::MAX {
            self.chat_view
                .total
                .saturating_sub(self.chat_view.area.height as usize) as i64
        } else {
            self.scroll_up as i64
        };
        // The renderer clamps the relative gesture to the actual content.
        self.scroll_up = (cur + delta).max(0) as usize;
        // Apply this gesture relative to the frame the user actually saw.
        // draw_chat resolves the resulting offset back into an absolute
        // anchor, which later streaming cannot move.
        self.chat_view.manual_top = None;
        self.needs_redraw = true;
    }

    pub(crate) fn handle_view_key(&mut self, key: KeyEvent, ctl: &Controller) {
        // Scroll keys work regardless of modifier bits: terminals that
        // report arrows with modifiers (kitty keyboard protocol and friends)
        // must still scroll the view. The view has no other arrow bindings.
        match key.code {
            KeyCode::Up => {
                self.view_scroll_by(-1);
                return;
            }
            KeyCode::Down => {
                self.view_scroll_by(1);
                return;
            }
            KeyCode::PageUp => {
                self.view_scroll_by(-5);
                return;
            }
            KeyCode::PageDown => {
                self.view_scroll_by(5);
                return;
            }
            KeyCode::Home => {
                if let Some(view) = self.view_overlay.as_mut() {
                    view.scroll = 0;
                    self.needs_redraw = true;
                }
                return;
            }
            KeyCode::End => {
                // Render clamps to the content height, so `usize::MAX` is
                // reliably the bottom of the view.
                if let Some(view) = self.view_overlay.as_mut() {
                    view.scroll = usize::MAX;
                    self.needs_redraw = true;
                }
                return;
            }
            _ => {}
        }
        if key.modifiers != KeyModifiers::NONE {
            return;
        }
        let event = match key.code {
            KeyCode::Esc => Some("cancel"),
            KeyCode::Enter => Some("submit"),
            _ => None,
        };
        if let Some(event) = event {
            if let Some(view) = self.view_overlay.take() {
                if view.notify_plugin {
                    ctl.send(Cmd::PluginOverlayEvent {
                        id: view.id,
                        event: event.into(),
                        value: None,
                    });
                }
            }
        }
    }

    pub(crate) fn handle_slider_key(&mut self, key: KeyEvent, ctl: &Controller) {
        if key.modifiers != KeyModifiers::NONE {
            return;
        }
        if key.code == KeyCode::Enter {
            if let Some(mut slider) = self.slider_overlay.take() {
                if slider.snap_to_marks {
                    if let Some(mark) = slider.marks.iter().min_by(|left, right| {
                        (left.value - slider.value)
                            .abs()
                            .total_cmp(&(right.value - slider.value).abs())
                    }) {
                        slider.value = mark.value;
                    }
                }
                ctl.send(Cmd::PluginOverlayEvent {
                    id: slider.id,
                    event: "submit".into(),
                    value: Some(serde_json::json!(slider.value)),
                });
            }
            return;
        }
        if key.code == KeyCode::Esc {
            if let Some(slider) = self.slider_overlay.take() {
                ctl.send(Cmd::PluginOverlayEvent {
                    id: slider.id,
                    event: "cancel".into(),
                    value: Some(serde_json::json!(slider.value)),
                });
            }
            return;
        }
        let direction = match key.code {
            KeyCode::Left => -1.0,
            KeyCode::Right => 1.0,
            _ => return,
        };
        let Some(slider) = self.slider_overlay.as_mut() else {
            return;
        };
        let next = (slider.value + direction * slider.step).clamp(slider.min, slider.max);
        if next == slider.value {
            return;
        }
        slider.value = next;
        ctl.send(Cmd::PluginOverlayEvent {
            id: slider.id.clone(),
            event: "change".into(),
            value: Some(serde_json::json!(slider.value)),
        });
    }

    pub(crate) fn handle_select_key(&mut self, key: KeyEvent, ctl: &Controller) {
        if let Some(select) = self.select_overlay.as_mut().filter(|select| select.searchable) {
            let edited = match (key.code, key.modifiers) {
                (KeyCode::Char('u'), KeyModifiers::CONTROL) => { select.query.clear(); true }
                (KeyCode::Char(ch), modifiers)
                    if (modifiers == KeyModifiers::NONE || modifiers == KeyModifiers::SHIFT)
                        && !ch.is_control() => {
                    if select.query.chars().count() < 256 { select.query.push(ch); }
                    true
                }
                (KeyCode::Backspace, KeyModifiers::NONE) => { select.query.pop(); true }
                _ => false,
            };
            if edited {
                select.reconcile_search();
                return;
            }
        }
        if key.modifiers != KeyModifiers::NONE {
            return;
        }
        if matches!(key.code, KeyCode::Delete | KeyCode::Backspace) {
            if !self.select_overlay.as_ref().is_some_and(|select|
                !select.visible_indices().is_empty()
                    && select.options.get(select.sel).is_some_and(|option| option.deletable && !option.disabled)) {
                return;
            }
            if let Some(select) = self.select_overlay.take() {
                ctl.send(Cmd::PluginOverlayEvent {
                    id: select.id,
                    event: "delete".into(),
                    value: Some(serde_json::json!(select.options[select.sel].value)),
                });
            }
            return;
        }
        if key.code == KeyCode::Enter {
            if self.select_overlay.as_ref().is_some_and(|select| select.visible_indices().is_empty() || select.options[select.sel].disabled) {
                return;
            }
            if let Some(select) = self.select_overlay.take() {
                let value = select.options[select.sel].value.clone();
                ctl.send(Cmd::PluginOverlayEvent {
                    id: select.id,
                    event: "submit".into(),
                    value: Some(serde_json::json!(value)),
                });
            }
            return;
        }
        if key.code == KeyCode::Esc {
            if let Some(select) = self.select_overlay.take() {
                let value = select.options[select.sel].value.clone();
                ctl.send(Cmd::PluginOverlayEvent {
                    id: select.id,
                    event: "cancel".into(),
                    value: Some(serde_json::json!(value)),
                });
            }
            return;
        }
        let Some(select) = self.select_overlay.as_mut() else {
            return;
        };
        let visible = select.visible_indices();
        if visible.is_empty() { return; }
        let position = visible.iter().position(|&index| index == select.sel).unwrap_or(0);
        let previous = select.sel;
        match key.code {
            KeyCode::Up => {
                select.sel = visible[position.saturating_sub(1)];
            }
            KeyCode::Down => {
                select.sel = visible[(position + 1).min(visible.len() - 1)];
            }
            KeyCode::Home => select.sel = visible[0],
            KeyCode::End => select.sel = visible[visible.len() - 1],
            _ => return,
        }
        if select.sel == previous {
            return;
        }
        select.value = select.options[select.sel].value.clone();
        ctl.send(Cmd::PluginOverlayEvent {
            id: select.id.clone(),
            event: "change".into(),
            value: Some(serde_json::json!(select.value)),
        });
    }

    pub(crate) fn handle_key(&mut self, key: KeyEvent, ctl: &Controller) {
        self.needs_redraw = true;
        // CROW_KEYDEBUG=1: surface exactly what the terminal delivered
        // (after CG rescue) in the tip row — kills keybinding mysteries.
        if self.key_debug {
            self.show_tip(self.locale.trf(
                "key: {} + {}",
                "按键：{} + {}",
                &[
                    format!("{:?}", key.modifiers),
                    format!("{:?}", key.code),
                ],
            ));
        }

        // Vim mode intercepts plain keys while it is active — but only
        // once every modal has had its chance: overlays and forms keep
        // their own key handling (the intercept therefore lives after the
        // modal blocks, so a vim Insert-mode Esc cancels the ask/picker
        // instead of toggling vim, and normal-mode letters never land in
        // a hidden composer while a modal is up).

        if key.modifiers == KeyModifiers::ALT && !self.pending_cordis_approvals.is_empty() {
            let decision = match key.code {
                KeyCode::Char('1') => Some("allow-version"),
                KeyCode::Char('2') => Some("allow-future"),
                KeyCode::Char('3') => Some("reject"),
                _ => None,
            };
            if let Some(decision) = decision {
                ctl.send(Cmd::RespondCordisApproval {
                    request_id: self.pending_cordis_approvals[0].request_id.clone(),
                    decision: decision.into(),
                });
                return;
            }
        }

        // Standard ACP form elicitation is the top-most modal.
        if self.elicitation_ask.is_some() {
            self.handle_elicitation_key(key);
            return;
        }

        // ACP tool permission sits above session pickers (Backchat ask panel).
        if self.permission_ask.is_some() {
            self.handle_permission_ask_key(key);
            return;
        }

        if self.view_overlay.is_some() {
            self.handle_view_key(key, ctl);
            return;
        }

        if self.select_overlay.is_some() {
            self.handle_select_key(key, ctl);
            return;
        }

        if self.slider_overlay.is_some() {
            self.handle_slider_key(key, ctl);
            return;
        }

        // --- model picker overlay steals input first (grok modal semantics)
        if self.picker.is_some() {
            self.handle_picker_key(key, ctl);
            return;
        }

        // --- /plugins tree popup (provider → plugin inventory)
        if self.plugin_tree.is_some() {
            self.handle_plugin_tree_key(key);
            return;
        }

        if self.agent_selection.is_some() {
            if key.modifiers == KeyModifiers::NONE {
                match key.code {
                    KeyCode::Left => self.move_agent_selection(-1),
                    KeyCode::Right => self.move_agent_selection(1),
                    KeyCode::Enter => self.confirm_agent_selection(),
                    KeyCode::Esc => self.cancel_agent_selection(),
                    _ => {}
                }
            }
            return;
        }

        if self.active_subagent.is_some() {
            if key.code == KeyCode::Char('q') && key.modifiers == KeyModifiers::NONE {
                self.handle_esc(ctl);
                return;
            }
            if key.code == KeyCode::Down && key.modifiers == KeyModifiers::NONE {
                self.begin_agent_navigation();
                return;
            }
            let ctx = crate::input::KeyCtx {
                input_empty: true,
                history_active: false,
            };
            if let Some(action) = crate::input::classify(&key, ctx) {
                match action {
                    Action::Esc
                    | Action::Quit
                    | Action::ToggleTheme
                    | Action::ScrollHalfUp
                    | Action::ScrollHalfDown
                    | Action::PageUp
                    | Action::PageDown
                    | Action::JumpTop
                    | Action::JumpTail => self.dispatch(action, ctl),
                    _ => {}
                }
            }
            return;
        }

        // Vim mode: plain keys become vim commands, but only with no
        // modal above (see the note at the top of this function).
        if self.vim.is_active()
            && self.elicitation_ask.is_none()
            && self.queue_edit.is_none()
            && !self.slash_completion_open()
        {
            if self.vim.handle_key(&key, &mut self.input) {
                self.reconcile_attachments();
                self.refresh_file_menu();
                return;
            }
        }

        // The @file browser owns its navigation keys while open; everything
        // else falls through to normal editing (which re-syncs the browser
        // through `refresh_file_menu`). Enter settles, Tab drills into a
        // directory, → follows the explorer's enter semantics.
        if let Some(menu) = &mut self.file_menu {
            // ctrl+h toggles hidden files/dirs (the explorer's own binding
            // for ToggleShowHidden); it stays modal while the browser is
            // open, like the navigation keys.
            if key.modifiers == KeyModifiers::CONTROL && key.code == KeyCode::Char('h') {
                crate::file_ref::navigate(menu, crate::file_ref::Input::ToggleShowHidden);
                return;
            }
            if key.modifiers == KeyModifiers::NONE {
                match key.code {
                    KeyCode::Up => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::Up);
                        return;
                    }
                    KeyCode::Down => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::Down);
                        return;
                    }
                    KeyCode::Home => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::Home);
                        return;
                    }
                    KeyCode::End => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::End);
                        return;
                    }
                    KeyCode::PageUp => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::PageUp);
                        return;
                    }
                    KeyCode::PageDown => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::PageDown);
                        return;
                    }
                    KeyCode::Left => {
                        crate::file_ref::navigate(menu, crate::file_ref::Input::Left);
                        return;
                    }
                    KeyCode::Right | KeyCode::Tab => {
                        self.file_menu_drill();
                        return;
                    }
                    KeyCode::Enter => {
                        self.file_menu_settle();
                        return;
                    }
                    KeyCode::Esc => {
                        self.dismiss_file_menu();
                        return;
                    }
                    _ => {}
                }
            }
        }

        if let Some(selected) = self.queue_selection {
            let n = self.prompt_queue.len();
            if n == 0 {
                self.queue_selection = None;
                return;
            }
            match (key.code, key.modifiers) {
                (KeyCode::Up, KeyModifiers::NONE) => {
                    self.queue_selection = Some(selected.checked_sub(1).unwrap_or(n - 1));
                }
                (KeyCode::Down, KeyModifiers::NONE) => {
                    self.queue_selection = Some((selected + 1) % n);
                }
                (KeyCode::Enter, KeyModifiers::NONE) => {
                    self.begin_queue_edit_at(selected.min(n - 1));
                }
                (KeyCode::Esc, KeyModifiers::NONE) => {
                    self.queue_selection = None;
                    self.show_tip(self.locale.tr("queue selection closed", "队列选择已关闭"));
                    if matches!(self.state, RunState::Idle) {
                        self.dispatch_next_queued(ctl);
                    }
                }
                _ => {}
            }
            return;
        }

        if key.code == KeyCode::Char('d')
            && key.modifiers == KeyModifiers::CONTROL
            && self.queue_edit.is_some()
        {
            if let Some(edit) = &mut self.queue_edit {
                edit.delete_confirm = true;
            }
            self.slash_completion_dismissed = true;
            self.show_tip(self.locale.tr(
                "delete queued prompt? · enter confirm · esc back",
                "删除这条排队消息？· enter 确认 · esc 返回",
            ));
            return;
        }

        if key.code == KeyCode::Down
            && key.modifiers == KeyModifiers::NONE
            && self.active_subagent.is_none()
            && self.input.is_empty()
            && self.input.hist_pos.is_none()
            && !self.subagents.is_empty()
        {
            self.begin_agent_navigation();
            return;
        }

        // The slash menu owns vertical arrows while it is visible. Ordinary
        // non-empty drafts use them for visual-line cursor motion below.
        if key.modifiers == KeyModifiers::NONE && self.slash_completion_open() {
            let n = self.slash_matches().len();
            if n > 0 {
                match key.code {
                    KeyCode::Up => self.slash_sel = self.slash_sel.checked_sub(1).unwrap_or(n - 1),
                    KeyCode::Down => self.slash_sel = (self.slash_sel + 1) % n,
                    _ => {}
                }
                if matches!(key.code, KeyCode::Up | KeyCode::Down) {
                    // The `/theme ` candidate popup previews the palette the
                    // highlight just landed on (mirrors the theme dialog).
                    self.preview_slash_theme();
                    return;
                }
            }
        }

        // Once Escape dismisses recommendations, the same single-line slash
        // draft participates in history navigation. The editor stash restores
        // it when Down returns past the newest history entry.
        if key.modifiers == KeyModifiers::NONE
            && self.slash_completion_dismissed
            && self.queue_edit.is_none()
        {
            match key.code {
                KeyCode::Up => {
                    self.history_prev_from_draft();
                    return;
                }
                KeyCode::Down => {
                    self.history_next();
                    return;
                }
                _ => {}
            }
        }

        let ctx = crate::input::KeyCtx {
            input_empty: self.input.is_empty(),
            history_active: self.input.hist_pos.is_some(),
        };
        if let Some(action) = crate::input::classify(&key, ctx) {
            self.dispatch(action, ctl);
        }
        // Any edit may have cut an [image n] token — the tray follows the
        // text (grok's lexicon-scan model).
        self.reconcile_attachments();
        // Caret/token changes drive the @file browser: open, navigate the
        // query's directory prefix, or close it.
        self.refresh_file_menu();
    }


    pub(crate) fn handle_esc(&mut self, ctl: &Controller) {
        if self.elicitation_ask.is_some() {
            self.finish_elicitation(crate::elicitation::ElicitationReply::Cancelled);
            return;
        }
        if self.permission_ask.is_some() {
            self.finish_permission_ask(PermissionAskReply::Cancelled);
            return;
        }
        if self.picker.is_some() {
            self.picker = None;
            return;
        }
        if self.active_subagent.take().is_some() {
            self.scroll_up = 0;
            self.sel = None;
            self.needs_redraw = true;
            return;
        }
        // A lingering copy highlight is dismissed first (idle only — while
        // running, esc keeps its interrupt meaning and clears it in passing).
        let had_chat_sel = self.sel.take().is_some();
        let had_input_sel = self.input_sel.take().is_some();
        if (had_chat_sel || had_input_sel) && matches!(self.state, RunState::Idle) {
            self.needs_redraw = true;
            return;
        }
        if self.slash_completion_open() {
            self.slash_completion_dismissed = true;
            return;
        }
        if let Some(edit) = &mut self.queue_edit {
            if edit.delete_confirm {
                edit.delete_confirm = false;
                self.show_tip(self.locale.tr(
                    "delete cancelled · still editing queued prompt",
                    "已取消删除 · 仍在编辑这条排队消息",
                ));
            } else {
                self.queue_edit = None;
                self.input.clear();
                self.input_sel = None;
                self.slash_completion_dismissed = false;
                self.reconcile_attachments();
                self.show_tip(self.locale.tr("queued prompt edit cancelled", "已取消编辑排队消息"));
                if matches!(self.state, RunState::Idle) {
                    self.dispatch_next_queued(ctl);
                }
            }
            return;
        }
        match self.state {
            RunState::Running | RunState::Starting => {
                // grok: Esc cancels immediately; the draft survives.
                if ctl.interrupt_now() {
                    ctl.send(Cmd::Interrupt {
                        session_id: self.session_id.clone(),
                    });
                    self.state_note = self.locale.tr("cancelling", "正在取消").into();
                } else {
                    self.show_tip(self.locale.tr("demo turn — it finishes on its own", "演示轮次 —— 会自动结束"));
                }
            }
            RunState::Idle => {
                // Esc clears the draft — inline [image n] chips live in it,
                // so staged images go with it (reconcile below).
                if !self.input.is_empty() {
                    self.input.history.push(self.input.buf());
                    self.input.clear();
                    self.reconcile_attachments();
                    self.show_tip(self.locale.tr("draft cleared — ↑ recalls it", "草稿已清空 —— ↑ 可找回"));
                    return;
                }
                self.show_tip(self.locale.tr(
                    "esc — idle · a running turn is interrupted with esc",
                    "esc — 空闲 · 运行中的轮次用 esc 中断",
                ));
            }
        }
    }

    pub(crate) fn handle_ctrl_c(&mut self, _ctl: &Controller) {
        if self.harness_switch_in_progress() {
            self.ctrl_c_armed = None;
            self.show_tip("Harness is switching — Ctrl+C ignored");
            return;
        }
        if !self.input.is_empty() {
            // Clearing the draft never counts as the first press of the
            // double-Ctrl+C quit chord.
            self.ctrl_c_armed = None;
            self.input.history.push(self.input.buf());
            self.input.clear();
            self.input_sel = None;
            self.reconcile_attachments();
            self.show_tip(self.locale.tr("draft cleared — ↑ recalls it", "草稿已清空 —— ↑ 可找回"));
            return;
        }
        let required = 2;
        let mut chord = self.ctrl_c_armed.take().unwrap_or(CtrlCQuitChord {
            started: Instant::now(),
            presses: 0,
            required,
        });
        chord.presses += 1;
        if chord.presses >= chord.required {
            self.quit = true;
            return;
        }
        let remaining = chord.required - chord.presses;
        self.ctrl_c_armed = Some(chord);
        self.show_tip(if remaining == 1 {
            self.locale
                .tr("press ctrl+c again to exit", "再按一次 ctrl+c 退出")
                .into()
        } else {
            self.locale.trf(
                "press ctrl+c {} more times to exit while the agent is running",
                "Agent 运行中，再按 {} 次 ctrl+c 退出",
                &[remaining.to_string()],
            )
        });
    }
}

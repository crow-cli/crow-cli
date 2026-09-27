//! asks: App methods for the asks surface (Phase 2 split).

use super::*;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::bus::{permission_ask_default_sel, PermissionAskOption, PermissionAskReply};

impl App {
    pub(crate) fn handle_permission_ask_key(&mut self, key: KeyEvent) {
        let n = self
            .permission_ask
            .as_ref()
            .map(|ask| ask.options.len().max(1))
            .unwrap_or(1);
        match key.code {
            KeyCode::Esc => self.finish_permission_ask(PermissionAskReply::Cancelled),
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.finish_permission_ask(PermissionAskReply::Cancelled);
            }
            KeyCode::Up => {
                if let Some(ask) = &mut self.permission_ask {
                    ask.sel = ask.sel.checked_sub(1).unwrap_or(n - 1);
                }
            }
            KeyCode::Down => {
                if let Some(ask) = &mut self.permission_ask {
                    ask.sel = (ask.sel + 1) % n;
                }
            }
            KeyCode::Enter => {
                let id = self
                    .permission_ask
                    .as_ref()
                    .and_then(|ask| ask.options.get(ask.sel).map(|o| o.option_id.clone()));
                self.finish_permission_ask(match id {
                    Some(id) => PermissionAskReply::Selected(id),
                    None => PermissionAskReply::Cancelled,
                });
            }
            _ => {}
        }
    }

    pub(crate) fn handle_elicitation_key(&mut self, key: KeyEvent) {
        let Some(ask) = &mut self.elicitation_ask else {
            return;
        };
        // The description pane scrolls without touching the form: PageUp /
        // PageDown always, Home / End only while the field is not a text
        // editor (typed answers keep their cursor keys). The render clamps
        // to the visible pane, so End reliably reaches the last row.
        let editing_text = ask.form.current_is_text();
        match key.code {
            KeyCode::PageUp => {
                ask.scroll = ask.scroll.saturating_sub(5);
                return;
            }
            KeyCode::PageDown => {
                ask.scroll = ask.scroll.saturating_add(5);
                return;
            }
            KeyCode::Home if !editing_text => {
                ask.scroll = 0;
                return;
            }
            KeyCode::End if !editing_text => {
                ask.scroll = usize::MAX;
                return;
            }
            _ => {}
        }
        let before = ask.form.index;
        let reply = ask.form.handle_key(key);
        if ask.form.index != before {
            // A new field owns a fresh pane; don't carry the old offset.
            ask.scroll = 0;
        }
        if let Some(reply) = reply {
            self.finish_elicitation(reply);
        }
    }

    pub(crate) fn finish_elicitation(&mut self, reply: crate::elicitation::ElicitationReply) {
        if let Some(mut ask) = self.elicitation_ask.take() {
            if let Some(tx) = ask.reply.take() {
                let _ = tx.send(reply);
            }
        }
        self.needs_redraw = true;
    }

    /// Route an incoming ACP permission ask to the session that owns it:
    /// the live view when the owning tab is on screen, otherwise the
    /// owning parked slot (the ask waits there and its tab is badged until
    /// the user returns). An ask whose session the tab model does not know
    /// falls back to the live view rather than silently cancelling the
    /// agent's tool call. Dropping an unanswered overlay cancels it.
    pub(crate) fn open_permission_ask(
        &mut self,
        session_id: &str,
        title: String,
        options: Vec<PermissionAskOption>,
        reply: tokio::sync::oneshot::Sender<PermissionAskReply>,
    ) {
        // acp_fs's builtin write-outside ask is authored in English; its
        // known strings localize here at render time. Anything else (plugin
        // and host asks) passes through untouched.
        let title = match title
            .strip_prefix("write ")
            .and_then(|rest| rest.strip_suffix(" · outside workspace"))
        {
            Some(path) => self.locale.trf(
                "write {} · outside workspace",
                "写入 {} · 工作区外",
                &[path.into()],
            ),
            None => title,
        };
        let mut options = options;
        for option in &mut options {
            match (option.option_id.as_str(), option.name.as_str()) {
                ("deny", "Deny") => option.name = self.locale.tr("Deny", "拒绝").into(),
                ("allow", "Allow write") => {
                    option.name = self.locale.tr("Allow write", "允许写入").into();
                }
                _ => {}
            }
        }
        let sel = permission_ask_default_sel(&options);
        let overlay = PermissionAskOverlay {
            title,
            sel,
            options,
            reply: Some(reply),
        };
        let belongs_to_live = session_id == self.session_id
            || self.subagents.iter().any(|v| v.id == session_id);
        if belongs_to_live {
            self.permission_ask = Some(overlay);
        } else if let Some(slot) = self
            .parked
            .iter_mut()
            .find(|slot| slot.id == session_id || slot.subagents.iter().any(|v| v.id == session_id))
        {
            // A parked session asked while out of view: keep the ask on its
            // tab — it must not float over the tab on screen.
            slot.permission_ask = Some(overlay);
        } else {
            self.show_tip(self.locale.tr(
                "permission ask from an unknown session — shown here",
                "未知会话的权限请求 —— 在此显示",
            ));
            self.permission_ask = Some(overlay);
        }
        self.needs_redraw = true;
    }

    /// Route an ACP elicitation form like [`Self::open_permission_ask`].
    /// `None` sessions are request-scoped elicitations (auth/config phase)
    /// with no tab to belong to — they surface on the live view.
    pub(crate) fn open_elicitation_ask(
        &mut self,
        session_id: Option<&str>,
        form: crate::elicitation::ElicitationForm,
        reply: tokio::sync::oneshot::Sender<crate::elicitation::ElicitationReply>,
    ) {
        let mut form_state = crate::elicitation::ElicitationFormState::new(form);
        form_state.locale = self.locale;
        let overlay = ElicitationAskOverlay {
            form: form_state,
            scroll: 0,
            reply: Some(reply),
        };
        let for_live = match session_id {
            None => true,
            Some(sid) => sid == self.session_id || self.subagents.iter().any(|v| v.id == sid),
        };
        if for_live {
            self.elicitation_ask = Some(overlay);
        } else if let Some(slot) = self
            .parked
            .iter_mut()
            .find(|slot| {
                session_id.is_some_and(|sid| slot.id == sid || slot.subagents.iter().any(|v| v.id == sid))
            })
        {
            slot.elicitation_ask = Some(overlay);
        } else {
            self.show_tip(self.locale.tr(
                "elicitation from an unknown session — shown here",
                "未知会话的表单请求 —— 在此显示",
            ));
            self.elicitation_ask = Some(overlay);
        }
        self.needs_redraw = true;
    }

    pub(crate) fn finish_permission_ask(&mut self, reply: PermissionAskReply) {
        if let Some(mut ask) = self.permission_ask.take() {
            if let Some(tx) = ask.reply.take() {
                let _ = tx.send(reply);
            }
        }
        self.needs_redraw = true;
    }
}

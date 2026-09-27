//! dispatch: App methods for the dispatch surface (Phase 2 split).

use super::*;
use crate::controller::Controller;
use crate::input::Action;
use crate::transcript::NoticeLevel;

impl App {
    /// Apply one classified [`Action`] — the only place key semantics touch
    /// app state, so `input::keymap` stays a pure table.
    pub(crate) fn dispatch(&mut self, action: Action, ctl: &Controller) {
        if matches!(
            action,
            Action::Insert(_)
                | Action::Newline
                | Action::Backspace
                | Action::DeleteForward
                | Action::DeleteWordBack
                | Action::KillToEnd
                | Action::KillToStart
                | Action::KillLine
                | Action::Undo
                | Action::Redo
                | Action::YankPaste
                | Action::SelectLeft
                | Action::SelectRight
                | Action::SelectUp
                | Action::SelectDown
                | Action::SelectWordLeft
                | Action::SelectWordRight
                | Action::SelectLineStart
                | Action::SelectLineEnd
        ) {
            self.slash_completion_dismissed = false;
            // Text edits invalidate the drag-selection highlight.
            self.input_sel = None;
        }
        match action {
            Action::Insert(ch) => {
                self.input.insert_char(ch);
                self.snap_slash_sel();
            }
            Action::Newline => {
                self.input.insert_newline();
            }
            Action::Enter => {
                self.input_sel = None;
                let menu = if self.slash_completion_open() {
                    self.slash_matches()
                } else {
                    Vec::new()
                };
                if !menu.is_empty() {
                    let entry = menu[self.slash_sel.min(menu.len() - 1)].clone();
                    self.accept_slash(&entry, ctl);
                } else if self.queue_edit.is_some() {
                    self.save_queue_edit(ctl);
                } else if self.input.is_empty()
                    && self.pending_images.is_empty()
                    && !self.prompt_queue.is_empty()
                {
                    self.send_queue_head_now(ctl);
                } else {
                    self.submit(ctl);
                }
            }
            Action::TabComplete => {
                self.slash_completion_dismissed = false;
                self.input_sel = None;
                let menu = self.slash_matches();
                if !menu.is_empty() {
                    let entry = &menu[self.slash_sel.min(menu.len() - 1)];
                    if entry.disabled { return; }
                    self.input.set(
                        entry
                            .completion
                            .clone()
                            .unwrap_or_else(|| format!("/{} ", entry.name)),
                    );
                    self.snap_slash_sel();
                }
            }
            Action::Esc => self.handle_esc(ctl),
            Action::CtrlC => self.handle_ctrl_c(ctl),
            Action::Quit => self.quit = true,
            Action::ClearScrollback => {
                self.transcript.clear();
                self.sel = None;
                    self.transcript.push_notice(
                        NoticeLevel::Info,
                        self.locale.tr("scrollback cleared", "滚动区已清空").into(),
                    );
            }
            Action::ToggleTheme => {
                self.toggle_theme_mode();
            }
            Action::ToggleExpandAll => {
                // Cells arrive open, so ctrl+o is the collapse-everything
                // override first and the restore second.
                self.transcript.collapse_all = !self.transcript.collapse_all;
                self.show_tip(if self.transcript.collapse_all {
                    self.locale
                        .tr("collapsed all thoughts and tool results", "已折叠全部思考与工具输出")
                } else {
                    self.locale
                        .tr("expanded all thoughts and tool results", "已展开全部思考与工具输出")
                });
            }
            Action::SendNow => self.send_now(ctl),
            Action::EditQueuedPrompt => self.open_queue_selector(),
            Action::AttachClipboard => self.clip_image("", ctl),
            Action::ModelPicker => self.open_model_picker(ctl),
            Action::CycleAgent => self.cycle_agent(ctl),
            Action::CyclePermission => self.cycle_permission(ctl),
            Action::HistoryPrev => self.history_prev(),
            Action::HistoryNext => self.history_next(),
            Action::ScrollHalfUp => self.scroll_by(10),
            Action::ScrollHalfDown => self.scroll_by(-10),
            Action::PageUp => self.scroll_by(20),
            Action::PageDown => self.scroll_by(-20),
            Action::JumpTop => {
                self.scroll_up = usize::MAX;
                self.chat_view.manual_top = None;
            }
            Action::JumpTail => {
                self.scroll_up = 0;
                self.chat_view.manual_top = None;
            }
            Action::CursorLeft => self.input.move_left(),
            Action::CursorRight => self.input.move_right(),
            Action::CursorUp => {
                let cursor = self.input.cursor_char();
                self.input.move_up();
                if self.queue_edit.is_none() && self.input.cursor_char() == cursor {
                    self.history_prev_from_draft();
                }
            }
            Action::CursorDown => self.input.move_down(),
            Action::WordLeft => self.input.word_left(),
            Action::WordRight => self.input.word_right(),
            Action::LineStart => self.input.line_start(self.composer_wrap_width),
            Action::LineEnd => self.input.line_end(self.composer_wrap_width),
            Action::Backspace => {
                // Deleting into an inline chip cuts the whole [image n]
                // token (and un-stages that image) instead of one bracket.
                if !self.delete_token_at(self.input.cursor_char(), true) {
                    self.input.backspace();
                }
            }
            Action::DeleteForward => {
                if !self.delete_token_at(self.input.cursor_char(), false) {
                    self.input.delete_forward();
                }
            }
            Action::DeleteWordBack => self.input.delete_word_back(),
            Action::KillToEnd => self.input.kill_to_end(self.composer_wrap_width),
            Action::KillToStart => self.input.kill_to_start(self.composer_wrap_width),
            Action::KillLine => self.input.kill_line(),
            Action::Undo => {
                self.input.undo();
            }
            Action::Redo => {
                self.input.redo();
            }
            Action::YankPaste => {
                self.input.paste_yank();
            }
            Action::SelectLeft => self.input.select_left(),
            Action::SelectRight => self.input.select_right(),
            Action::SelectUp => self.input.select_up(),
            Action::SelectDown => self.input.select_down(),
            Action::SelectWordLeft => self.input.select_word_left(),
            Action::SelectWordRight => self.input.select_word_right(),
            Action::SelectLineStart => self.input.select_line_start(),
            Action::SelectLineEnd => self.input.select_line_end(),
            Action::CopySelection => {
                // Keyboard selection first, then the mouse-drag selection.
                if let Some(text) = self.input.selection_text() {
                    if !text.trim().is_empty() {
                        self.input.copy_selection_to_yank();
                        self.copy_text(&text);
                    }
                } else if let Some((a, b)) = self.input_selection_range() {
                    let text = self.input.chars_between(a, b);
                    if !text.trim().is_empty() {
                        self.copy_text(&text);
                    }
                }
            }
            Action::CutSelection => {
                // Keyboard selection first, then the mouse-drag selection.
                if let Some(text) = self.input.selection_text() {
                    if !text.trim().is_empty() {
                        self.input.cut_selection_to_yank();
                        self.copy_text(&text);
                    } else {
                        self.show_tip(self.locale.tr(
                        "nothing to cut — select with shift+arrows",
                        "无可剪切 —— 用 shift+方向键先选中文本",
                    ));
                    }
                } else if let Some((a, b)) = self.input_selection_range() {
                    let text = self.input.chars_between(a, b);
                    if !text.trim().is_empty() {
                        self.input.delete_char_range(a, b);
                        self.input_sel = None;
                        self.copy_text(&text);
                    } else {
                        self.show_tip(self.locale.tr(
                        "nothing to cut — select with shift+arrows",
                        "无可剪切 —— 用 shift+方向键先选中文本",
                    ));
                    }
                } else {
                    self.show_tip(self.locale.tr(
                        "nothing to cut — select with shift+arrows",
                        "无可剪切 —— 用 shift+方向键先选中文本",
                    ));
                }
            }
        }
    }
}

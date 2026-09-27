//! mouse: App methods for the mouse surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use unicode_width::UnicodeWidthChar;
use crate::bus::Cmd;
use crate::controller::Controller;

impl App {
    /// grok-build mouse semantics, scaled down: wheel scrolls; left-drag
    /// selects with a live highlight (auto-scrolling at the pane edges) and
    /// copies on release; double-click selects & copies a word. Shift+drag
    /// bypasses capture in most terminals → native selection still works.
    pub(crate) fn handle_mouse(&mut self, mouse: MouseEvent, ctl: &Controller) {
        match mouse.kind {
            MouseEventKind::ScrollUp => {
                if self.elicitation_ask.is_some() {
                    self.elicitation_scroll_by(-3);
                } else if self.permission_ask.is_some() {
                    self.permission_ask_scroll_by(-1);
                } else if let Some(tree) = &mut self.plugin_tree {
                    tree.state.scroll_up(3);
                } else if self.view_overlay.is_some() {
                    self.view_scroll_by(-3);
                } else if self.select_overlay.is_some() {
                    self.handle_select_key(KeyEvent::new(KeyCode::Up, KeyModifiers::NONE), ctl);
                    self.needs_redraw = true;
                } else if self.picker.is_some() {
                    self.picker_scroll_by(-1);
                } else {
                    self.mouse_scroll(3, mouse.column, mouse.row);
                }
            }
            MouseEventKind::ScrollDown => {
                if self.elicitation_ask.is_some() {
                    self.elicitation_scroll_by(3);
                } else if self.permission_ask.is_some() {
                    self.permission_ask_scroll_by(1);
                } else if let Some(tree) = &mut self.plugin_tree {
                    tree.state.scroll_down(3);
                } else if self.view_overlay.is_some() {
                    self.view_scroll_by(3);
                } else if self.select_overlay.is_some() {
                    self.handle_select_key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE), ctl);
                    self.needs_redraw = true;
                } else if self.picker.is_some() {
                    self.picker_scroll_by(1);
                } else {
                    self.mouse_scroll(-3, mouse.column, mouse.row);
                }
            }
            MouseEventKind::Down(MouseButton::Left) => {
                self.needs_redraw = true;
                // Session tab strip (issue #94): left-click a tab switches.
                if let Some(tab) = self.tab_at(mouse.column, mouse.row) {
                    self.switch_view_to_tab(tab, ctl);
                    // Clicking the strip's outermost visible tab also
                    // nudges the strip so its neighbor appears — repeated
                    // edge clicks walk the mouse through every session
                    // tab, left or right. `switch_view_to_tab` already
                    // released overlays etc.; only the strip moves here.
                    let first = self
                        .tab_rects
                        .iter()
                        .map(|(_, idx)| *idx)
                        .min()
                        .unwrap_or(tab);
                    let last = self
                        .tab_rects
                        .iter()
                        .map(|(_, idx)| *idx)
                        .max()
                        .unwrap_or(tab);
                    if tab == first && tab > 0 {
                        self.tab_strip_offset = self.tab_strip_offset.saturating_sub(1);
                        self.needs_redraw = true;
                    } else if tab == last && tab + 1 < self.session_tab_count() {
                        self.tab_strip_offset = self.tab_strip_offset.saturating_add(1);
                        self.needs_redraw = true;
                    }
                    return;
                }
                if let Some(action) = self
                    .slot_actions
                    .iter()
                    .find(|(rect, _)| {
                        mouse.column >= rect.x
                            && mouse.column < rect.right()
                            && mouse.row >= rect.y
                            && mouse.row < rect.bottom()
                    })
                    .map(|(_, action)| action.clone())
                {
                    self.sel = None;
                    self.selecting = false;
                    self.last_click = None;
                    self.input_selecting = false;
                    match action {
                        crate::slots::TuiAction::Command { name, args } => {
                            ctl.send(Cmd::InvokePluginCommand { name, args });
                        }
                    }
                    return;
                }
                // Clicking a tool block toggles its expand/collapse instead of
                // starting a text selection.
                if let Some(ci) = self.tool_at(mouse.column, mouse.row) {
                    self.sel = None;
                    self.selecting = false;
                    self.last_click = None;
                    self.input_selecting = false;
                    self.toggle_tool(ci);
                    return;
                }
                // The ↥ prompt-jump button (issue #103) wins over caret
                // placement: each click walks the chat view to the previous
                // user prompt (newest first, wrapping at the oldest).
                if self.elicitation_ask.is_none()
                    && self.active_subagent.is_none()
                    && self.prompt_jump_btn_hit(mouse.column, mouse.row)
                {
                    self.sel = None;
                    self.selecting = false;
                    self.last_click = None;
                    self.input_selecting = false;
                    self.input_sel = None;
                    self.jump_to_user_prompt();
                    return;
                }
                // The mouse-only expand button (issue #92) wins over caret
                // placement inside the well: clicking toggles the input
                // height instead of moving the caret. It lives inside the
                // well, so it is only live outside child views and the
                // elicitation form (which owns its own field).
                if self.elicitation_ask.is_none()
                    && self.active_subagent.is_none()
                    && self.expand_btn_hit(mouse.column, mouse.row)
                {
                    self.sel = None;
                    self.selecting = false;
                    self.last_click = None;
                    self.input_selecting = false;
                    self.input_sel = None;
                    self.input_expanded = !self.input_expanded;
                    self.needs_redraw = true;
                    return;
                }
                // Click inside the composer well: place the caret at the
                // clicked char and arm an input drag-selection. Like any
                // click outside the chat pane, the chat highlight is
                // dismissed first. The elicitation form owns its own field
                // and child-view chrome replaces the composer, so the
                // hidden caret stays put in both cases.
                if self.elicitation_ask.is_none()
                    && self.active_subagent.is_none()
                    && self.input_hit(mouse.column, mouse.row)
                {
                    self.sel = None;
                    self.selecting = false;
                    self.last_click = None;
                    let cell = self.input_cell_at(mouse.column, mouse.row);
                    let offset = self.input.screen_to_char(self.input_avail(), cell.0, cell.1);
                    self.input.set_cursor_char(offset);
                    self.input_sel = Some(InputSel {
                        anchor: cell,
                        head: cell,
                    });
                    self.input_selecting = true;
                    self.refresh_file_menu();
                    return;
                }
                let Some(p) = self.chat_hit(mouse.column, mouse.row) else {
                    // Click outside the chat pane dismisses the highlight.
                    self.sel = None;
                    self.selecting = false;
                    self.input_sel = None;
                    self.input_selecting = false;
                    return;
                };
                self.input_sel = None;
                self.input_selecting = false;
                let double = self.last_click.take().is_some_and(|(at, x, y)| {
                    at.elapsed() < DOUBLE_CLICK_WINDOW
                        && x.abs_diff(mouse.column) <= 1
                        && y == mouse.row
                });
                self.last_click = Some((Instant::now(), mouse.column, mouse.row));
                if double {
                    self.select_word_at(p);
                } else {
                    self.sel = Some(Selection { anchor: p, head: p });
                    self.selecting = true;
                }
            }
            MouseEventKind::Drag(MouseButton::Left) if self.selecting => {
                // Edge auto-scroll (grok: compute_autoscroll): dragging
                // past the pane keeps scrolling while events arrive.
                let a = self.chat_view.area;
                if mouse.row < a.y {
                    self.scroll_by(2);
                } else if mouse.row >= a.y.saturating_add(a.height) {
                    self.scroll_by(-2);
                }
                let head = self.chat_clamp(mouse.column, mouse.row);
                if let Some(sel) = &mut self.sel {
                    sel.head = head;
                }
                self.needs_redraw = true;
            }
            MouseEventKind::Drag(MouseButton::Left) if self.input_selecting => {
                // The head snaps to the well edges: drags above select to
                // the top visible row, below it to the bottom row.
                let head = self.input_cell_at(mouse.column, mouse.row);
                if let Some(sel) = &mut self.input_sel {
                    sel.head = head;
                }
                self.needs_redraw = true;
            }
            MouseEventKind::Up(MouseButton::Left) if self.selecting => {
                self.selecting = false;
                self.finish_selection();
            }
            MouseEventKind::Up(MouseButton::Left) if self.input_selecting => {
                self.input_selecting = false;
                self.finish_input_selection();
            }
            MouseEventKind::Moved => {
                // grok-style hover: track which inline chip the pointer is
                // over; redraw only on changes (mouse moves are a firehose).
                self.mouse_pos = Some((mouse.column, mouse.row));
                let over_btn = self.expand_btn_hit(mouse.column, mouse.row);
                if over_btn != self.hover_expand_btn {
                    self.hover_expand_btn = over_btn;
                    self.needs_redraw = true;
                }
                let over_jump = self.prompt_jump_btn_hit(mouse.column, mouse.row);
                if over_jump != self.hover_prompt_jump_btn {
                    self.hover_prompt_jump_btn = over_jump;
                    self.needs_redraw = true;
                }
                let hover = self.chip_at(mouse.column, mouse.row);
                if hover != self.hover_att {
                    self.hover_att = hover;
                    self.needs_redraw = true;
                }
            }
            _ => {}
        }
    }

    /// Char-index spans of live `[image n]` tokens in the draft, sorted by
    /// position: `(start, end_exclusive, attachment idx)`.
    pub fn token_spans(&self) -> Vec<(usize, usize, usize)> {
        let buf = self.input.buf();
        let mut spans = Vec::new();
        for (idx, att) in self.pending_images.iter().enumerate() {
            if let Some(byte) = buf.find(&att.token) {
                let start = buf[..byte].chars().count();
                spans.push((start, start + att.token.chars().count(), idx));
            }
        }
        spans.sort_unstable();
        spans
    }

    /// Cut the whole token when `cursor` deletes into one (backward: the
    /// char left of the cursor; forward: the char at it). Returns whether
    /// a token was cut.
    pub(crate) fn delete_token_at(&mut self, cursor: usize, backward: bool) -> bool {
        let probe = if backward {
            let Some(p) = cursor.checked_sub(1) else {
                return false;
            };
            p
        } else {
            cursor
        };
        let Some(&(start, end, idx)) = self
            .token_spans()
            .iter()
            .find(|(s, e, _)| probe >= *s && probe < *e)
        else {
            return false;
        };
        self.input.delete_char_range(start, end);
        if let Some(att) = self.pending_images.remove(idx) {
            self.show_tip(self.locale.trf("removed {}", "已移除 {}", &[att.name.clone()]));
        }
        true
    }

    /// Drop attachments whose token no longer survives in the draft text.
    pub(crate) fn reconcile_attachments(&mut self) {
        if self.pending_images.reconcile(&self.input.buf()) > 0 {
            self.hover_att = None;
            self.needs_redraw = true;
        }
    }

    /// The chip to preview: mouse hover wins, else the chip the text
    /// cursor sits in or immediately after (“光标在附近”).
    pub fn preview_att(&self) -> Option<usize> {
        if let Some(idx) = self.hover_att {
            return Some(idx);
        }
        let c = self.input.cursor_char();
        self.token_spans()
            .iter()
            .find(|(s, e, _)| c >= *s && c <= *e)
            .map(|&(_, _, idx)| idx)
    }

    /// Hit-test the mouse-only composer expand button (issue #92). The
    /// button's rect is recorded by the painter every frame, so the
    /// pointer can discover it while moving across the card's top-right.
    pub(crate) fn expand_btn_hit(&self, col: u16, row: u16) -> bool {
        self.expand_btn.is_some_and(|r| {
            col >= r.x
                && col < r.x.saturating_add(r.width)
                && row >= r.y
                && row < r.y.saturating_add(r.height)
        })
    }

    /// Hit-test the mouse-only `↥` user-prompt jump button (issue #103).
    pub(crate) fn prompt_jump_btn_hit(&self, col: u16, row: u16) -> bool {
        self.prompt_jump_btn.is_some_and(|r| {
            col >= r.x
                && col < r.x.saturating_add(r.width)
                && row >= r.y
                && row < r.y.saturating_add(r.height)
        })
    }

    /// `↥` click (issue #103): jump the chat view to a user prompt. The
    /// first click goes to the newest prompt, each further click walks one
    /// prompt back, and the oldest wraps to the newest again. The last
    /// target is remembered in memory only (never persisted) and rides
    /// across clicks, so jumping resumes where the previous jump stopped.
    pub(crate) fn jump_to_user_prompt(&mut self) {
        let area = self.chat_view.area;
        if area.width == 0 || area.height == 0 {
            return;
        }
        let theme = self.theme;
        let spinner = self.spinner();
        let layout = self.transcript.layout(
            &theme,
            self.tone_mode,
            area.width,
            spinner,
            crate::pet::kitty_supported(),
        );
        if layout.users.is_empty() {
            self.show_tip(self.locale.tr(
                "no user prompts yet — ↥ finds them once you send one",
                "还没有用户输入 —— 发送后 ↥ 即可跳转",
            ));
            return;
        }
        // The running indicator rides as one extra tail line in draw_chat;
        // include it so the anchored viewport matches the next frame.
        let total = layout.lines.len()
            + usize::from(matches!(self.state, RunState::Starting | RunState::Running));
        let h = area.height as usize;
        let max_scroll = total.saturating_sub(h);
        let target = match self
            .prompt_jump_cell
            .and_then(|cell| layout.users.iter().position(|p| p.cell == cell))
        {
            // A previous jump: continue walking backward from it…
            Some(rank) if rank > 0 => layout.users[rank - 1],
            // …and the oldest prompt wraps back to the newest.
            Some(_) => layout.users[layout.users.len() - 1],
            // No previous jump (fresh session, tab switch, or the target
            // cell is gone): start at the newest prompt.
            None => layout.users[layout.users.len() - 1],
        };
        let from_newest = layout
            .users
            .iter()
            .rposition(|p| p.cell == target.cell)
            .map(|rank| layout.users.len() - rank)
            .unwrap_or(1);
        self.prompt_jump_cell = Some(target.cell);
        // Anchor the prompt's first line to the top of the chat pane and
        // flash its rows for a few seconds (issue #103).
        let start = target.line.min(max_scroll);
        let end = start.saturating_add(h).min(total);
        let scroll_up = total.saturating_sub(end);
        self.chat_view.manual_top = (scroll_up > 0).then_some(start);
        self.scroll_up = scroll_up;
        self.prompt_flash = Some((target.cell, Instant::now() + PROMPT_FLASH_TTL));
        self.needs_redraw = true;
        self.show_tip(self.locale.trf(
            "↥ user prompt {k}/{n} · newest first",
            "↥ 用户输入 {k}/{n} · 从最新往前",
            &[from_newest.to_string(), layout.users.len().to_string()],
        ));
    }

    /// Hit-test a screen cell against the inline chips drawn this frame.
    pub(crate) fn chip_at(&self, col: u16, row: u16) -> Option<usize> {
        self.att_chips
            .iter()
            .find(|(r, _)| {
                col >= r.x
                    && col < r.x.saturating_add(r.width)
                    && row >= r.y
                    && row < r.y.saturating_add(r.height)
            })
            .map(|(_, idx)| *idx)
    }

    /// Hit-test a screen cell against the chat pane; `None` outside it.
    pub(crate) fn chat_hit(&self, col: u16, row: u16) -> Option<SelPoint> {
        let a = self.chat_view.area;
        if self.chat_view.lines.is_empty()
            || col < a.x
            || col >= a.x.saturating_add(a.width)
            || row < a.y
            || row >= a.y.saturating_add(a.height)
        {
            return None;
        }
        // The snapshot covers only the viewport: clamp the screen row to it
        // (content shorter than the pane) — absolute line = top + rel.
        let rel = ((row - a.y) as usize).min(self.chat_view.lines.len() - 1);
        Some(SelPoint {
            line: self.chat_view.top + rel,
            col: (col - a.x) as usize,
        })
    }

    /// Like `chat_hit`, but clamps to the pane so drags outside it still
    /// extend the selection to the nearest edge.
    pub(crate) fn chat_clamp(&self, col: u16, row: u16) -> SelPoint {
        let a = self.chat_view.area;
        let col = col.clamp(a.x, a.x.saturating_add(a.width.saturating_sub(1)));
        let row = row.clamp(a.y, a.y.saturating_add(a.height.saturating_sub(1)));
        self.chat_hit(col, row)
            .unwrap_or(SelPoint { line: 0, col: 0 })
    }

    /// The transcript cell that owns the line under a screen cell, if any.
    pub(crate) fn tool_at(&self, col: u16, row: u16) -> Option<usize> {
        let p = self.chat_hit(col, row)?;
        self.chat_view.line_owner(p.line)
    }

    /// Mouse wheel always scrolls the conversation, including over tool cards.
    pub(crate) fn mouse_scroll(&mut self, delta: i64, _col: u16, _row: u16) {
        self.scroll_by(delta);
    }

    /// Scroll the open plugin view overlay (wheel and keyboard share this
    /// path). The renderer clamps to the actual content height, so a large
    /// value (End) reliably reaches the bottom.
    pub(crate) fn view_scroll_by(&mut self, delta: i64) {
        if let Some(view) = self.view_overlay.as_mut() {
            if delta < 0 {
                view.scroll = view.scroll.saturating_sub(delta.unsigned_abs() as usize);
            } else {
                view.scroll = view.scroll.saturating_add(delta as usize);
            }
            self.needs_redraw = true;
        }
    }

    /// Scroll the markdown description pane of the open ACP elicitation form
    /// (wheel and keyboard share this path). The renderer clamps to the
    /// visible pane height, so `usize::MAX` (End) reaches the last row.
    pub(crate) fn elicitation_scroll_by(&mut self, delta: i64) {
        if let Some(ask) = self.elicitation_ask.as_mut() {
            if delta < 0 {
                ask.scroll = ask.scroll.saturating_sub(delta.unsigned_abs() as usize);
            } else {
                ask.scroll = ask.scroll.saturating_add(delta as usize);
            }
            self.needs_redraw = true;
        }
    }

    /// Wheel-scroll the open picker — the `/resume` session list, `/model`,
    /// `/mode`, … One notch moves the selection exactly like one ↑/↓ press
    /// (the highlight sweeps through a static window; the window itself only
    /// scrolls once the selection leaves it — see `draw_model_picker`).
    /// Steps clamp at both ends; only the arrows wrap, so an overscrolled
    /// notch never teleports the highlight to the list tail.
    pub(crate) fn picker_scroll_by(&mut self, delta: i64) {
        let Some(picker) = &mut self.picker else { return };
        let kind = picker.kind;
        let sel_before = picker.sel;
        let last = picker.items.len().saturating_sub(1);
        if delta < 0 {
            picker.sel = picker
                .sel
                .saturating_sub(delta.unsigned_abs() as usize)
                .min(last);
        } else {
            picker.sel = picker.sel.saturating_add(delta as usize).min(last);
        }
        self.needs_redraw = true;
        // One notch equals one ↑/↓ press, so the theme dialog previews the
        // pack the wheel moved the highlight onto.
        if kind == PickerKind::Theme
            && self
                .picker
                .as_ref()
                .is_some_and(|picker| picker.sel != sel_before)
        {
            self.preview_picker_theme();
        }
    }

    /// Wheel over an ACP permission ask (which floats above host pickers)
    /// moves its highlight, mirroring the ↑/↓ keys and the modal priority
    /// of `handle_key` — an ask on top of the `/resume` picker must not
    /// scroll the picker underneath it.
    pub(crate) fn permission_ask_scroll_by(&mut self, delta: i64) {
        let Some(ask) = &mut self.permission_ask else { return };
        let last = ask.options.len().saturating_sub(1);
        if delta < 0 {
            ask.sel = ask
                .sel
                .saturating_sub(delta.unsigned_abs() as usize)
                .min(last);
        } else {
            ask.sel = ask.sel.saturating_add(delta as usize).min(last);
        }
        self.needs_redraw = true;
    }

    /// Toggle a tool between its collapsed viewport and full expansion.
    pub(crate) fn toggle_tool(&mut self, ci: usize) {
        let label = {
            let Some(cell) = self.displayed_transcript_mut().cells.get_mut(ci) else {
                return;
            };
            cell.expanded = !cell.expanded;
            if cell.expanded {
                "expanded"
            } else {
                "collapsed"
            }
        };
        self.show_tip(self.locale.trf(
            "{} tool output · click toggles",
            "{} 工具输出 · 点击切换展开",
            &[label.into()],
        ));
        self.needs_redraw = true;
    }

    /// grok `finish_text_drag`: reconstruct the dragged text and copy it —
    /// the highlight persists only when something actually reached the
    /// clipboard path. A plain click (caret) just clears the highlight.
    pub(crate) fn finish_selection(&mut self) {
        self.needs_redraw = true;
        let Some(sel) = self.sel else { return };
        if sel.is_caret() {
            self.sel = None;
            return;
        }
        let text = self.selection_text(sel);
        if text.trim().is_empty() {
            self.sel = None;
            return;
        }
        self.copy_text(&text);
    }

    pub(crate) fn copy_text(&mut self, text: &str) {
        let chars = text.chars().count();
        if crate::clipboard::copy(text) {
            self.show_tip(self.locale.trf(
                "✓ copied {} chars — esc clears the highlight",
                "✓ 已复制 {} 个字符 —— esc 清除高亮",
                &[chars.to_string()],
            ));
        } else {
            self.show_tip(self.locale.tr(
                "copy failed — hold shift and drag for the terminal's native selection",
                "复制失败 —— 按住 shift 拖动可使用终端原生选择",
            ));
        }
    }

    /// True when the screen cell lies inside the composer input well.
    pub(crate) fn input_hit(&self, col: u16, row: u16) -> bool {
        let a = self.input_area;
        a.width > 0
            && a.height > 0
            && col >= a.x
            && col < a.x.saturating_add(a.width)
            && row >= a.y
            && row < a.y.saturating_add(a.height)
    }

    /// Display-cell width of the composer text area, matching
    /// `ui::draw_input` (`area.width - prompt width`).
    pub(crate) fn input_avail(&self) -> usize {
        let a = self.input_area;
        let pw = "❯ "
            .chars()
            .map(|c| c.width().unwrap_or(0).max(1))
            .sum::<usize>();
        a.width.saturating_sub(pw as u16).max(1) as usize
    }

    /// Map a screen cell to a text-area cell `(row, col)` in the same
    /// coordinates as `Input::char_index_at` (prompt offset and viewport
    /// scroll applied), clamped into the visible well.
    pub(crate) fn input_cell_at(&self, col: u16, row: u16) -> (usize, usize) {
        let a = self.input_area;
        let pw = "❯ "
            .chars()
            .map(|c| c.width().unwrap_or(0).max(1))
            .sum::<usize>();
        let rel_row = (row.saturating_sub(a.y) as usize)
            .min(a.height.saturating_sub(1) as usize)
            .saturating_add(self.input_top);
        let rel_col = (col.saturating_sub(a.x.saturating_add(pw as u16)) as usize)
            .min(self.input_avail().saturating_sub(1));
        (rel_row, rel_col)
    }

    /// Ordered char boundaries covered by the composer selection — both
    /// endpoint cells inclusive, so a drag in either direction covers
    /// exactly the cells the pointer crossed. `None` without a selection.
    pub(crate) fn input_selection_range(&mut self) -> Option<(usize, usize)> {
        let sel = self.input_sel?;
        let (s, e) = if sel.anchor <= sel.head {
            (sel.anchor, sel.head)
        } else {
            (sel.head, sel.anchor)
        };
        let avail = self.input_avail();
        let start = self.input.screen_to_char(avail, s.0, s.1);
        let end = self.input.screen_to_char_end(avail, e.0, e.1);
        (start < end).then_some((start, end))
    }

    /// Copy the dragged composer selection; the highlight persists until
    /// the next click or Esc, mirroring the chat pane. A plain click
    /// (caret) just clears the highlight.
    pub(crate) fn finish_input_selection(&mut self) {
        self.needs_redraw = true;
        let Some(sel) = self.input_sel else { return };
        if sel.anchor == sel.head {
            self.input_sel = None;
            return;
        }
        let Some((a, b)) = self.input_selection_range() else {
            self.input_sel = None;
            return;
        };
        let text = self.input.chars_between(a, b);
        if text.trim().is_empty() {
            self.input_sel = None;
            return;
        }
        self.copy_text(&text);
    }

    /// Extract the selected text from the layout snapshot: cell-range slices
    /// per line, trailing whitespace trimmed, joined with newlines. The
    /// snapshot is viewport-sized: a selection anchored above/below what the
    /// frame showed (stale after scrolling) copies its visible part.
    pub fn selection_text(&self, sel: Selection) -> String {
        let lines = &self.chat_view.lines;
        if lines.is_empty() {
            return String::new();
        }
        let top = self.chat_view.top;
        let (s, e) = sel.ordered();
        if e.line < top {
            return String::new(); // selection entirely above the viewport
        }
        let first = s.line.saturating_sub(top);
        let last = (e.line - top).min(lines.len() - 1);
        if first > last {
            return String::new(); // starts below the captured viewport
        }
        let mut out = Vec::with_capacity(last - first + 1);
        for (li, text) in lines.iter().enumerate().take(last + 1).skip(first) {
            let c0 = if li + top == s.line { s.col } else { 0 };
            let c1 = if li + top == e.line { e.col + 1 } else { usize::MAX };
            out.push(slice_by_cells(text, c0, c1).trim_end().to_string());
        }
        out.join("\n")
    }

    /// Double-click: select the whitespace-delimited word under the pointer
    /// and copy it right away (grok's word select & copy).
    pub(crate) fn select_word_at(&mut self, p: SelPoint) {
        let Some(line) = self.chat_view.line_text(p.line) else {
            return;
        };
        let Some((col, width, word)) = word_span(line, p.col) else {
            self.sel = None;
            return;
        };
        self.sel = Some(Selection {
            anchor: SelPoint { line: p.line, col },
            head: SelPoint {
                line: p.line,
                col: col + width - 1,
            },
        });
        self.selecting = false;
        let word = word.clone();
        self.copy_text(&word);
    }
}

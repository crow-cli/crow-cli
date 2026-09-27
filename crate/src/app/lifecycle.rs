//! lifecycle: App methods for the lifecycle surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crate::transcript::Transcript;

impl App {
    pub fn spinner(&self) -> char {
        SPINNER[self.spinner_idx % SPINNER.len()]
    }

    pub fn displayed_transcript(&self) -> &Transcript {
        self.active_subagent
            .as_deref()
            .and_then(|id| self.subagents.iter().find(|view| view.id == id))
            .map(|view| &view.transcript)
            .unwrap_or(&self.transcript)
    }

    /// Scrollback bound — the crow_cli.tui `prune_window` hysteresis, fired
    /// from `draw_chat` with the height `row_count` just measured. Returns the
    /// rows removed so the caller can re-measure.
    ///
    /// Pruning shifts every cell index and bumps the transcript generation, so
    /// it refuses to run while an index is outstanding anywhere: a steer echo
    /// waiting to be hidden, or a local shell waiting to write its output into
    /// its cell. Both are short-lived, and the bound is soft by design — the
    /// transcript simply runs a little past the high mark until they settle.
    pub(crate) fn prune_scrollback(&mut self, rows: usize) -> usize {
        if rows <= crate::transcript::PRUNE_HIGH_ROWS {
            return 0;
        }
        if !self.pending_steer_cells.is_empty() || !self.shell_pending.is_empty() {
            return 0;
        }
        let removed = self.displayed_transcript_mut().prune_oldest(rows);
        if removed == 0 {
            return 0;
        }
        // The rows vanished above the viewport, so an absolute scroll anchor
        // has to move up with them or the view jumps to different content.
        if let Some(top) = &mut self.chat_view.manual_top {
            *top = top.saturating_sub(removed);
        }
        // The ↥ jump cursor indexes cells that just moved; crow-cli drops its
        // block cursor on prune for the same reason.
        self.prompt_jump_cell = None;
        self.show_tip(self.locale.trf(
            "scrollback pruned — oldest {} rows dropped",
            "已裁剪滚动区 —— 丢弃最旧的 {} 行",
            &[removed.to_string()],
        ));
        removed
    }

    pub fn displayed_transcript_mut(&mut self) -> &mut Transcript {
        if let Some(index) = self
            .active_subagent
            .as_deref()
            .and_then(|id| self.subagents.iter().position(|view| view.id == id))
        {
            return &mut self.subagents[index].transcript;
        }
        &mut self.transcript
    }


    /// Re-detect the workspace git branch for the composer cap label. One
    /// in-process read of `.git/HEAD` (no subprocess), at most every
    /// `GIT_CHECK_INTERVAL` — unless forced right after a session shell
    /// command, when the user may have just run `!git checkout …`.
    pub(crate) fn refresh_git_branch(&mut self, force: bool) {
        if !force && self.git_check_at.elapsed() < GIT_CHECK_INTERVAL {
            return;
        }
        self.git_check_at = Instant::now();
        let branch = crate::ui::head_branch(&self.cfg.workspace);
        if branch != self.git_branch {
            self.git_branch = branch;
            self.needs_redraw = true;
        }
    }

    pub fn tick(&mut self) {
        // The cap's ":branch" label tracks mid-session checkouts (agent
        // `bash` tool, another terminal) on a throttled cadence.
        self.refresh_git_branch(false);
        if self.state != RunState::Idle
            || self.transcript.streaming()
            || self
                .subagents
                .iter()
                .any(|view| view.running || view.transcript.streaming())
        {
            self.spinner_idx = self.spinner_idx.wrapping_add(1);
            self.needs_redraw = true;
        }
        if let Some((_, at)) = &self.tip {
            if at.elapsed() > TIP_TTL {
                self.tip = None;
                self.needs_redraw = true;
            }
        }
        // The ↥ jump flash restores the prompt to normal after its 5 s.
        if let Some((_, until)) = &self.prompt_flash {
            if Instant::now() >= *until {
                self.prompt_flash = None;
                self.prompt_flash_lines = None;
                self.needs_redraw = true;
            }
        }
        // disarm expired chords
        if let Some(chord) = self.ctrl_c_armed {
            if chord.started.elapsed() > CTRL_C_QUIT_WINDOW {
                self.ctrl_c_armed = None;
            }
        }
    }

    pub fn show_tip(&mut self, text: impl Into<String>) {
        self.tip = Some((text.into(), Instant::now()));
        self.needs_redraw = true;
    }
}

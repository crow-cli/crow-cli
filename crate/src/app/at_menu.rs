//! at_menu: App methods for the at_menu surface (Phase 2 split).

use super::*;
use crate::input::VimMode;

impl App {
    /// Re-scan the composer line at the caret and sync the `@file` browser:
    /// open it on an active token (unless the same token was Esc-dismissed
    /// or vim normal mode is active), re-navigate on query edits, close it
    /// when the token is gone.
    pub(crate) fn refresh_file_menu(&mut self) {
        // Vim normal mode is command editing — no mention browser.
        if self.vim.is_active() && self.vim.mode == VimMode::Normal {
            self.file_menu = None;
            return;
        }
        // The slash menu and the @ menu are mutually exclusive.
        if self.slash_completion_open() {
            self.file_menu = None;
            return;
        }
        let (row, col) = self.input.char_to_rowcol(self.input.cursor_char());
        let Some(line) = self.input.lines().get(row).cloned() else {
            self.file_menu = None;
            return;
        };
        let Some(token) = crate::file_ref::active_at_token(&line, col) else {
            // The token is gone (draft cleared, caret left it): a fresh
            // `@` must be able to reopen the browser, so drop the
            // dismissal tag along with the menu.
            self.file_menu = None;
            self.file_menu_dismissed = None;
            return;
        };
        let tag = crate::file_ref::token_tag(token.quoted, &token.query);
        if let Some(menu) = &mut self.file_menu {
            if menu.row() != row || menu.start() != token.start || menu.end() != token.end {
                menu.retoken(row, &token);
            }
            menu.apply_query(&token.query);
        } else {
            // Esc-dismissed tokens stay closed until their text changes.
            if self.file_menu_dismissed.as_deref() == Some(tag.as_str()) {
                return;
            }
            self.file_menu_dismissed = None;
            if let Some(mut menu) = crate::file_ref::FileMenu::open(
                std::path::Path::new(&self.cfg.workspace),
                row,
                &token,
            ) {
                // The token may already carry a query (dismissed-token
                // reopen): drive the browser to it before showing.
                menu.apply_query(&token.query);
                self.file_menu = Some(menu);
            }
        }
    }

    /// `Enter` on the selected entry: replace the token with `@path` (or
    /// `@dir/` for directories) and close the browser.
    pub(crate) fn file_menu_settle(&mut self) {
        let Some(mention) = self.file_menu.as_ref().and_then(|m| m.current_mention()) else {
            return;
        };
        let (row, start, end) = {
            let menu = self.file_menu.as_ref().expect("checked above");
            (menu.row(), menu.start(), menu.end())
        };
        crate::file_ref::replace_span(&mut self.input, row, start, end, &mention);
        self.file_menu = None;
        self.input_sel = None;
        self.reconcile_attachments();
    }

    /// `Tab` on a directory: rewrite the token to `@dir/` (quoted form
    /// keeps the quote open) and keep the browser inside the directory.
    /// `Tab` on a file settles like `Enter`.
    pub(crate) fn file_menu_drill(&mut self) {
        let Some(menu) = self.file_menu.as_ref() else {
            return;
        };
        if menu.explorer().files().is_empty() {
            return;
        }
        let file = menu.explorer().current().clone();
        if !file.is_dir {
            self.file_menu_settle();
            return;
        }
        let rel = crate::file_ref::relative_path(menu.base(), &file.path);
        let Some(mention) = crate::file_ref::format_file_mention(&rel, true, menu.quoted()) else {
            return;
        };
        let (row, start) = (menu.row(), menu.start());
        let end = start + mention.chars().count();
        crate::file_ref::replace_span(&mut self.input, row, menu.start(), menu.end(), &mention);
        if let Some(menu) = &mut self.file_menu {
            menu.retoken(row, &crate::file_ref::AtToken {
                start,
                end,
                query: format!("{rel}/"),
                quoted: mention.starts_with("@\""),
            });
            menu.apply_query(&format!("{rel}/"));
        }
    }

    /// Esc: close the browser and remember the token so it stays closed
    /// until its text changes.
    pub(crate) fn dismiss_file_menu(&mut self) {
        if let Some(menu) = &self.file_menu {
            self.file_menu_dismissed = Some(crate::file_ref::token_tag(
                menu.quoted(),
                &menu.token_query(),
            ));
        }
        self.file_menu = None;
    }
}

//! theme: App methods for the theme surface (Phase 2 split).

use super::*;
use crate::bus::Cmd;
use crate::controller::Controller;
use crate::transcript::NoticeLevel;

impl App {
    pub(crate) fn apply_palette_rpc(&mut self, params: &serde_json::Value) {
        match crate::theme::parse_palette_notification(params) {
            Ok(Some(n)) => self.merge_palette(n.pack, n.activate),
            Ok(None) => {}
            Err(err) => self.show_tip(self.locale.trf(
                "palette ignored: {}",
                "已忽略主题包：{}",
                &[err.to_string()],
            )),
        }
        self.needs_redraw = true;
    }

    pub(crate) fn remove_palette_rpc(&mut self, params: &serde_json::Value) {
        if params.get("protocol").and_then(serde_json::Value::as_u64) != Some(0) {
            return;
        }
        let Some(id) = params.get("id").and_then(serde_json::Value::as_str) else {
            return;
        };
        if id == "default" {
            return;
        }
        if self.active_palette_id == id {
            self.activate_palette("default");
        }
        self.palettes.retain(|palette| palette.id != id);
        self.needs_redraw = true;
    }

    pub(crate) fn merge_palette(&mut self, pack: crate::theme::PalettePack, activate: bool) {
        let id = pack.id.clone();
        let loaded = pack.loaded;
        if let Some(existing) = self.palettes.iter_mut().find(|p| p.id == id) {
            *existing = pack;
        } else {
            self.palettes.push(pack);
        }
        if !loaded && self.active_palette_id == id {
            self.activate_palette("default");
        } else if activate && loaded {
            self.activate_palette(&id);
        } else if loaded && self.active_palette_id == id {
            self.sync_theme_from_active();
        }
    }

    pub(crate) fn activate_palette(&mut self, id: &str) {
        let Some(pack) = self.palettes.iter().find(|p| p.id == id) else {
            return;
        };
        let preferred = pack.preferred_mode;
        // A commit (Enter, or the palette arrival of a pending Enter)
        // supersedes any preview still on screen.
        self.theme_preview = None;
        self.theme_pending = None;
        self.active_palette_id = id.to_string();
        // A pack that owns a mode is entered in it: picking Catppuccin Latte
        // means a light UI, not Latte's dark counterpart. Packs that own none
        // (every Plugin pack, `default`) keep the mode already in effect.
        if let Some(mode) = preferred {
            self.theme.mode = mode;
        }
        self.sync_theme_from_active();
        self.save_settings();
        self.show_tip(self.locale.trf(
            "theme: {} {}",
            "主题：{} {}",
            &[
                self.active_palette_id.clone(),
                self.theme.mode.as_str().to_string(),
            ],
        ));
    }

    pub(crate) fn select_palette(&mut self, id: &str, ctl: &Controller) {
        let Some(palette) = self
            .palettes
            .iter()
            .find(|palette| palette.id == id)
            .cloned()
        else {
            return;
        };
        if palette.loaded {
            self.activate_palette(id);
        } else {
            self.show_tip(self.locale.trf(
                "loading theme plugin for {}…",
                "正在加载主题插件 {}…",
                &[id.to_string()],
            ));
            // Enter confirmed this pack: paint its registered colors right
            // away and keep them on screen while the Plugin loads, so the
            // commit never flashes back to the previous theme. The loaded
            // palette arrival converts the pending preview into the
            // committed theme (`activate_palette`).
            if self.active_palette_id != id {
                let committed = self.committed_theme_mode();
                self.theme = palette.theme(palette.preferred_mode.unwrap_or(committed));
                self.theme_preview = Some((id.to_string(), committed));
                self.theme_pending = Some(id.to_string());
                self.needs_redraw = true;
            }
        }
        ctl.send(Cmd::PluginThemeSelected {
            agent_id: self.session_id.clone(),
            id: id.into(),
        });
    }

    pub(crate) fn sync_theme_from_active(&mut self) {
        let mode = self.theme.mode;
        if let Some(pack) = self
            .palettes
            .iter()
            .find(|p| p.id == self.active_palette_id)
        {
            self.theme = pack.theme(mode);
        }
    }

    /// The mode the committed palette is painted in. While a preview is
    /// live, `theme.mode` belongs to the previewed pack, so the committed
    /// mode is the one the preview recorded when it started.
    pub(crate) fn committed_theme_mode(&self) -> crate::theme::Mode {
        self.theme_preview
            .as_ref()
            .map_or(self.theme.mode, |(_, mode)| *mode)
    }

    /// Live-switch the painter to a palette's colors without committing it:
    /// arrows over the theme dialog rows or the `/theme ` slash candidates
    /// only *preview*. The committed palette stays `active_palette_id`
    /// until Enter (`select_palette`); Esc or a moved highlight restores
    /// the committed theme. Stopped packs carry their full token maps from
    /// registration, so previews are pixel-exact either way.
    pub(crate) fn preview_palette(&mut self, id: &str) {
        if self.active_palette_id == id {
            // Highlight back on the committed pack — nothing to preview.
            self.clear_theme_preview();
            return;
        }
        let committed = self.committed_theme_mode();
        // A pack that owns a mode previews in it: arrowing onto Catppuccin
        // Latte shows Latte, which is what Enter will commit — not the dark
        // counterpart the current mode would otherwise pick out of it.
        let Some(preview) = self
            .palettes
            .iter()
            .find(|palette| palette.id == id)
            .map(|pack| pack.theme(pack.preferred_mode.unwrap_or(committed)))
        else {
            return;
        };
        self.theme = preview;
        self.theme_preview = Some((id.to_string(), committed));
        // A different palette was previewed → the pending Enter commit for
        // the previous one is stale; only Enter re-arms it.
        if self.theme_pending.as_deref().is_some_and(|pending| pending != id) {
            self.theme_pending = None;
        }
        self.needs_redraw = true;
    }

    /// Drop a pending palette preview and repaint the committed theme.
    pub(crate) fn clear_theme_preview(&mut self) {
        let committed = self.theme_preview.take().map(|(_, mode)| mode);
        if committed.is_some() || self.theme_pending.is_some() {
            self.theme_pending = None;
            // A flavor pack previewed in its own mode: put the committed
            // mode back before repainting, or Esc would leave the committed
            // pack in the preview's light/dark.
            if let Some(mode) = committed {
                self.theme.mode = mode;
            }
            self.sync_theme_from_active();
            self.needs_redraw = true;
        }
    }

    /// The palette id under the open `/theme ` slash popup highlight — never
    /// the dark/light toggle row. Callers resolve it against the catalog.
    pub(crate) fn slash_theme_candidate(&self) -> Option<String> {
        if self.slash_completion_dismissed {
            return None;
        }
        let matches = self.slash_matches();
        if matches.is_empty() {
            return None;
        }
        let entry = matches.get(self.slash_sel.min(matches.len() - 1))?;
        if entry.plugin || entry.skill || entry.name != "theme" {
            return None;
        }
        entry
            .completion
            .as_deref()
            .and_then(|completion| completion.strip_prefix("/theme "))
            .filter(|arg| *arg != "toggle")
            .map(str::to_string)
    }

    /// The open theme dialog applies the row under the highlight.
    pub(crate) fn preview_picker_theme(&mut self) {
        let Some(id) = self.picker.as_ref().and_then(|picker| {
            (picker.kind == PickerKind::Theme)
                .then(|| picker.items.get(picker.sel))
                .flatten()
                .map(|item| item.id.clone())
        }) else {
            return;
        };
        self.preview_palette(&id);
    }

    /// The open `/theme ` slash popup applies the palette candidate under
    /// the highlight; non-palette rows (`toggle` dark/light) never fire.
    pub(crate) fn preview_slash_theme(&mut self) {
        if let Some(id) = self.slash_theme_candidate() {
            self.preview_palette(&id);
        }
    }

    /// A palette preview only lives while its row is still highlighted (or
    /// its Enter commit is still loading its Plugin). Every handled event
    /// ends here, so Esc, a closed list, a moved highlight or an edited
    /// draft reverts to the committed theme — preview never sticks.
    pub(crate) fn reconcile_theme_preview(&mut self) {
        let Some((preview, _)) = self.theme_preview.clone() else {
            return;
        };
        let still_highlighted = self.picker.as_ref().is_some_and(|picker| {
            picker.kind == PickerKind::Theme
                && picker.items.get(picker.sel).is_some_and(|item| item.id == preview)
        }) || self.slash_theme_candidate().as_deref() == Some(preview.as_str());
        let commit_loading = self.theme_pending.as_deref() == Some(preview.as_str());
        if !still_highlighted && !commit_loading {
            self.clear_theme_preview();
        }
    }

    pub(crate) fn apply_theme_arg(&mut self, arg: &str, ctl: &Controller) {
        match arg {
            "" => self.open_theme_picker(),
            "toggle" => self.toggle_theme_mode(),
            id => {
                if self.palettes.iter().any(|p| p.id == id) {
                    self.select_palette(id, ctl);
                } else {
                    self.show_tip(self.locale.trf(
                        "unknown palette: {}",
                        "未知主题包：{}",
                        &[id.to_string()],
                    ));
                    self.transcript.push_notice(
                        NoticeLevel::Warn,
                        self.locale
                            .trf("unknown palette `{}`", "未知主题包 `{}`", &[id.to_string()]),
                    );
                }
            }
        }
    }

    pub(crate) fn toggle_theme_mode(&mut self) {
        // Toggle the *committed* mode: a live preview paints a pack that may
        // own its own mode, and ctrl+t is about the theme you keep.
        let next = match self.committed_theme_mode() {
            crate::theme::Mode::Dark => crate::theme::Mode::Light,
            crate::theme::Mode::Light => crate::theme::Mode::Dark,
        };
        match self.theme_preview.as_mut() {
            // The preview keeps painting its own pack; only the mode Esc
            // falls back to changes.
            Some((_, committed)) => *committed = next,
            None => self.theme = self.theme.toggled(),
        }
        self.save_settings();
        self.show_tip(self.locale.trf(
            "theme: {} {}",
            "主题：{} {}",
            &[self.active_palette_id.clone(), next.as_str().to_string()],
        ));
    }

    pub(crate) fn open_theme_picker(&mut self) {
        let items = self
            .palettes
            .iter()
            .map(|pack| PickerItem {
                id: pack.id.clone(),
                label: pack.label.clone(),
                meta: if pack.id == self.active_palette_id {
                    format!("{} · active", pack.source)
                } else if pack.loaded {
                    format!("{} · ready", pack.source)
                } else {
                    format!("{} · stopped", pack.source)
                },
                provider: None,
            })
            .collect::<Vec<_>>();
        let sel = items
            .iter()
            .position(|item| item.id == self.active_palette_id)
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Theme,
            title: self
                .locale
                .tr(
                    " theme · ↑↓ preview · enter apply · esc close · ctrl+t ",
                    " 主题 · ↑↓ 预览 · enter 确定 · esc 关闭 · ctrl+t ",
                )
                .into(),
            sel,
            items,
        });
    }

    /// Forget every session's delivery state: the runtime that owned it is
    /// gone, so nothing queued will ever be sent and nothing running will ever
    /// settle. Tabs and their transcripts survive — this is the reset both a
    /// runtime exit and a harness switch leave behind.
    pub(crate) fn clear_delivery_state(&mut self) {
        self.startup_bound = false;
        self.prompt_pending = false;
        self.queued = 0;
        self.prompt_queue.clear();
        self.queue_selection = None;
        self.queue_edit = None;
        self.pending_steer_cells.clear();
        for slot in &mut self.parked {
            // The dead runtime owned every session's delivery state,
            // not just the viewed one.
            slot.running = false;
            slot.prompt_pending = false;
            slot.prompt_queue.clear();
            slot.queue_selection = None;
            slot.queue_edit = None;
            slot.pending_steer_cells.clear();
        }
        if self.state != RunState::Idle {
            self.state = RunState::Idle;
            self.run_started = None;
        }
    }
}

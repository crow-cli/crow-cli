//! prefs: App methods for the prefs surface (Phase 2 split).

use super::*;
use crate::locale::{Locale, UiSettings};
use crate::runtime::{legacy_settings_paths, settings_path, RuntimeConfig};

impl App {
    pub(crate) fn locale_settings_path(cfg: &RuntimeConfig) -> std::path::PathBuf {
        settings_path(&cfg.session_root)
    }

    pub(crate) fn load_settings(cfg: &RuntimeConfig) -> UiSettings {
        let current = Self::locale_settings_path(cfg);
        if let Some(settings) = std::fs::read_to_string(&current)
            .ok()
            .and_then(|text| serde_json::from_str::<UiSettings>(&text).ok())
        {
            return settings;
        }
        // A current file that exists but does not parse is quarantined by the
        // next save; until then fall through to the legacy files rather than
        // silently dropping the user's preferences.
        for legacy in legacy_settings_paths(&cfg.session_root) {
            let Some((text, settings)) = std::fs::read_to_string(&legacy).ok().and_then(|text| {
                serde_json::from_str::<UiSettings>(&text)
                    .ok()
                    .map(|settings| (text, settings))
            }) else {
                continue;
            };
            if let Some(dir) = current.parent() {
                let _ = std::fs::create_dir_all(dir);
            }
            if !current.exists() {
                let _ = std::fs::write(&current, text);
            }
            return settings;
        }
        UiSettings::default()
    }

    pub(crate) fn save_settings(&self) {
        let path = Self::locale_settings_path(&self.cfg);
        if let Some(dir) = path.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        let mut current = settings_document(&path);
        current["language"] = serde_json::json!(self.locale);
        current["theme"] = serde_json::json!(self.active_palette_id);
        current["themeMode"] = serde_json::json!(self.committed_theme_mode().as_str());
        current["markdownTone"] = serde_json::json!(self.tone_mode.as_str());
        if let Ok(text) = serde_json::to_string_pretty(&current) {
            let _ = write_settings_atomic(&path, &text);
        }
    }

    pub(crate) fn set_locale(&mut self, arg: &str) {
        let next = if arg.trim().is_empty() {
            self.locale.alternate()
        } else if let Some(locale) = Locale::parse(arg) {
            locale
        } else {
            self.show_tip(
                self.locale
                    .tr("usage: /lang [zh|en]", "用法：/lang [zh|en]"),
            );
            return;
        };
        self.locale = next;
        // New notices from every transcript (live, parked, subagent views)
        // render in the switched language; cells already pushed keep theirs.
        self.transcript.locale = next;
        for slot in &mut self.parked {
            slot.transcript.locale = next;
            for view in &mut slot.subagents {
                view.transcript.locale = next;
            }
        }
        for view in &mut self.subagents {
            view.transcript.locale = next;
        }
        self.save_settings();
        self.show_tip(match next {
            Locale::En => "Language switched to English",
            Locale::Zh => "界面语言已切换为中文",
        });
        self.needs_redraw = true;
    }
}

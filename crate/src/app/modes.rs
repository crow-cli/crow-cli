//! modes: App methods for the modes surface (Phase 2 split).

use super::*;
use crate::bus::Cmd;
use crate::controller::Controller;

impl App {
    pub(crate) fn open_mode_picker(&mut self, ctl: &Controller) {
        ctl.send(Cmd::FetchCatalog {
            session_id: self.session_id.clone(),
        });
        let items: Vec<PickerItem> = if self.demo {
            AGENT_MODES
                .iter()
                .map(|(id, name, desc)| PickerItem {
                    id: id.to_string(),
                    label: name.to_string(),
                    meta: desc.to_string(),
                    provider: None,
                })
                .collect()
        } else {
            self.last_presets
                .iter()
                .map(|p| PickerItem {
                    id: p.id.clone(),
                    label: p.name.clone(),
                    meta: if p.broken {
                        format!("⚠ broken · {}", p.description)
                    } else {
                        p.description.clone()
                    },
                    provider: None,
                })
                .collect()
        };
        let current = self.current_mode();
        let sel = items.iter().position(|i| i.id == current).unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Mode,
            title: self
                .locale
                .tr(
                    " agent · enter select · esc close ",
                    " Agent · enter 选择 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    /// The effective composition id: folded `agent-preset/selected` / ACP
    /// `config_option_update`, else the demo stock default.
    pub fn current_mode(&self) -> String {
        self.modes.agent_preset.clone().unwrap_or_else(|| {
            if self.demo {
                "standard".into()
            } else {
                self.last_presets
                    .first()
                    .map(|p| p.id.clone())
                    .unwrap_or_default()
            }
        })
    }

    /// Resolve a protocol preset id through the latest ACP catalog. Demo mode
    /// uses its local stock catalog; unknown ids remain readable as-is.
    pub fn agent_label(&self, id: &str) -> String {
        self.last_presets
            .iter()
            .find(|preset| preset.id == id)
            .map(|preset| preset.name.clone())
            .or_else(|| {
                self.demo
                    .then(|| {
                        AGENT_MODES
                            .iter()
                            .find(|(preset_id, _, _)| *preset_id == id)
                            .map(|(_, name, _)| (*name).to_string())
                    })
                    .flatten()
            })
            .unwrap_or_else(|| id.to_string())
    }

    /// Pick the agent preset composed on this session's first prompt. The
    /// host locks it once the session agent exists (`/new` for a fresh one).
    pub(crate) fn set_mode(&mut self, preset: String, ctl: &Controller) {
        let label = self.agent_label(&preset);
        if self.modes.agent_preset.as_deref() == Some(preset.as_str()) {
            self.show_tip(self.locale.trf("agent already {}", "Agent 已是 {}", &[label.into()]));
            return;
        }
        ctl.send(Cmd::SetPreset {
            session_id: self.session_id.clone(),
            preset: preset.clone(),
        });
        // Preset scopes can mount their own skill registries.
        ctl.send(Cmd::FetchSkills {
            session_id: self.session_id.clone(),
        });
        self.show_tip(self.locale.trf("agent → {} …", "Agent → {} …", &[label.into()]));
    }

    /// Ctrl+Shift+A cycles the advertised agent presets directly. `/agent`
    /// keeps the picker for explicit selection; the shortcut mirrors
    /// Shift+Tab's one-keystroke permission switching.
    pub(crate) fn cycle_agent(&mut self, ctl: &Controller) {
        let current = self.current_mode();
        let choices: Vec<&str> = if self.demo {
            AGENT_MODES.iter().map(|(id, _, _)| *id).collect()
        } else {
            self.last_presets
                .iter()
                .map(|preset| preset.id.as_str())
                .collect()
        };
        let Some(next) = choices
            .iter()
            .position(|id| *id == current)
            .map(|index| choices[(index + 1) % choices.len()])
            .or_else(|| choices.first().copied())
        else {
            ctl.send(Cmd::FetchCatalog {
                session_id: self.session_id.clone(),
            });
            self.show_tip(self.locale.tr("agent presets unavailable", "Agent 预设不可用"));
            return;
        };
        self.set_mode(next.to_string(), ctl);
    }

    pub(crate) fn select_model(&mut self, item: PickerItem, ctl: &Controller) {
        let model = item.id;
        let provider = item.provider;
        let provider_changed = provider
            .as_deref()
            .is_some_and(|candidate| candidate != self.cfg.provider);
        if model != self.cfg.model || provider_changed {
            self.cfg.model = model.clone();
            self.selected_model = Some(model.clone());
            if let Some(p) = &provider {
                self.cfg.provider = p.clone();
            }
            ctl.send(Cmd::SelectModel {
                session_id: self.session_id.clone(),
                provider,
                model: Some(model.clone()),
                effort: None,
            });
        }
        // Stage 2: offer efforts for the chosen model.
        ctl.send(Cmd::FetchEfforts {
            session_id: self.session_id.clone(),
            provider: self.cfg.provider.clone(),
            model: self.cfg.model.clone(),
        });
    }

    pub(crate) fn set_model(&mut self, model: String, ctl: &Controller) {
        if model == self.cfg.model {
            return;
        }
        self.cfg.model = model.clone();
        self.selected_model = Some(model.clone());
        ctl.send(Cmd::SelectModel {
            session_id: self.session_id.clone(),
            provider: None,
            model: Some(model),
            effort: None,
        });
    }

    /// grok: Shift+Tab cycles the permission preset.
    pub(crate) fn cycle_permission(&mut self, ctl: &Controller) {
        let current = self.current_permission().to_string();
        let next = if self.permission_choices.len() >= 2 {
            let idx = self
                .permission_choices
                .iter()
                .position(|p| p.id == current)
                .unwrap_or(0);
            self.permission_choices[(idx + 1) % self.permission_choices.len()]
                .id
                .clone()
        } else {
            let idx = PERMISSION_PRESETS
                .iter()
                .position(|(p, _)| *p == current)
                .unwrap_or(0);
            PERMISSION_PRESETS[(idx + 1) % PERMISSION_PRESETS.len()]
                .0
                .to_string()
        };
        self.set_permission(next, ctl);
    }

    /// The effective model: an explicit `/model` pick until a turn realizes
    /// it, then the model that actually streamed last, then the configured
    /// default. Mirrors the meta-row chip chain, so the model picker
    /// highlights and ✓-marks the model the session is running (issue #102).
    pub fn current_model(&self) -> String {
        self.selected_model
            .clone()
            .or_else(|| self.transcript.last_model.clone())
            .unwrap_or_else(|| self.cfg.model.clone())
    }

    /// The effective permission preset: the folded `permission/preset` fact,
    /// or the harness default (workspace-write) before the session reports.
    pub fn current_permission(&self) -> &str {
        self.modes
            .permission
            .as_deref()
            .unwrap_or("workspace-write")
    }

    /// Ask the host to switch this session's permission preset; the durable
    /// `permission/preset` event echoes back and folds the ⛨ chip. Before
    /// the first prompt the host stages the switch and applies it when the
    /// session is created.
    pub(crate) fn set_permission(&mut self, preset: String, ctl: &Controller) {
        if self.modes.permission.as_deref() == Some(preset.as_str()) {
            self.show_tip(self.locale.trf(
                "permission already {}",
                "权限预设已是 {}",
                &[preset.into()],
            ));
            return;
        }
        ctl.send(Cmd::SetPermission {
            session_id: self.session_id.clone(),
            preset: preset.clone(),
        });
        self.show_tip(self.locale.trf(
            "permission → {} …",
            "权限预设 → {} …",
            &[preset.into()],
        ));
    }

    /// `/permission` — the two stock presets with their meaning, the current
    /// one preselected (picker twin of the blind shift+tab cycle).
    pub(crate) fn open_permission_picker(&mut self) {
        let reported = self.modes.permission.clone();
        let current = self.current_permission().to_string();
        let items = if self.permission_choices.is_empty() {
            PERMISSION_PRESETS
                .iter()
                .map(|(id, desc)| {
                    let mark = if reported.as_deref() == Some(*id) {
                        " · current"
                    } else if reported.is_none() && *id == current {
                        " · default"
                    } else {
                        ""
                    };
                    PickerItem {
                        id: id.to_string(),
                        label: permission_label(id),
                        meta: format!("{desc}{mark}"),
                        provider: None,
                    }
                })
                .collect()
        } else {
            permission_picker_items(&self.permission_choices, reported.as_deref(), &current)
        };
        let sel = items.iter().position(|i| i.id == current).unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Permission,
            title: self
                .locale
                .tr(
                    " permission · enter apply · esc close ",
                    " 权限 · enter 应用 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }
}

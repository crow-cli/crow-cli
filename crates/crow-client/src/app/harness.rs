//! harness: App methods for the harness surface (Phase 2 split).

use super::*;
use crate::bus::Cmd;
use crate::controller::Controller;
use crate::runtime::settings_path;
use crate::transcript::NoticeLevel;

impl App {
    /// `settings.json` as `/harness` sees it — the same path `agent_argv`
    /// resolves at boot, so the picker lists exactly what a restart would.
    pub(crate) fn harness_settings_path(&self) -> std::path::PathBuf {
        settings_path(&self.cfg.session_root)
    }

    pub(crate) fn open_harness_picker(&mut self) {
        let path = self.harness_settings_path();
        let current = crate::harness::current_id(&path);
        let items = crate::harness::all(&path)
            .into_iter()
            .map(|entry| {
                let active = current.as_deref() == Some(entry.id.as_str());
                let command = entry.command_text();
                PickerItem {
                    id: entry.id,
                    label: entry.label,
                    meta: if active {
                        format!("{command} · active")
                    } else {
                        command
                    },
                    provider: None,
                }
            })
            .collect::<Vec<_>>();
        if items.is_empty() {
            self.show_tip(self.locale.tr(
                "no harnesses configured — add one to settings.json first",
                "尚未配置 Harness —— 请先在 settings.json 中添加",
            ));
            return;
        }
        let sel = current
            .as_deref()
            .and_then(|id| items.iter().position(|item| item.id == id))
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Harness,
            title: self
                .locale
                .tr(
                    " harness · enter switch · esc close ",
                    " Harness · enter 切换 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    /// `/harness <id>`: persist the choice, then hand the resolved argv to the
    /// controller — it owns the endpoint, so it owns the respawn.
    ///
    /// The connection is replaced, not multiplexed: crow's ACP stack has
    /// one negotiated connection for every tab, so the sessions belonging to the
    /// old agent go with it. Their transcripts stay readable and the viewed tab
    /// rebinds to whatever the new connection's setup produces.
    pub(crate) fn switch_harness(&mut self, id: &str, ctl: &Controller) {
        let id = id.trim();
        let path = self.harness_settings_path();
        let entries = crate::harness::all(&path);
        let Some(entry) = entries.iter().find(|entry| entry.id == id) else {
            self.show_tip(self.locale.trf(
                "unknown harness: {} — /harness lists them",
                "未知 Harness：{} —— 用 /harness 列出全部",
                &[id.to_string()],
            ));
            return;
        };
        let label = entry.label.clone();
        if crate::harness::current_id(&path).as_deref() == Some(id) {
            self.show_tip(self.locale.trf(
                "{} is already the active harness",
                "{} 已经是当前 Harness",
                &[label],
            ));
            return;
        }
        let argv = entry.harness.argv();
        if let Err(err) = persist_default_harness(&path, id) {
            self.transcript.push_notice(
                NoticeLevel::Error,
                self.locale.trf(
                    "could not save the default harness: {}",
                    "无法保存默认 Harness：{}",
                    &[err.to_string()],
                ),
            );
            return;
        }
        self.picker = None;
        self.cancel_plugin_overlays(ctl);
        self.clear_delivery_state();
        self.awaiting_binds.clear();
        ctl.send(Cmd::SwitchHarness { argv });
        let notice = self
            .locale
            .trf("⟲ harness → {}", "⟲ Harness → {}", &[label]);
        // The transcript copy is the durable one: it marks where the agent, and
        // with it the protocol, changed. But a pane that has not sent a prompt
        // yet draws the welcome banner instead of the transcript, so on a fresh
        // start that copy is invisible — the same reason `TuiOpDone` tips. A
        // switch drops every session; the user has to be told at the time.
        self.transcript
            .push_notice(NoticeLevel::Info, notice.clone());
        if self.show_banner {
            self.show_tip(notice);
        }
        self.needs_redraw = true;
    }

    pub(crate) fn open_ui_plugin_picker(&mut self) {
        let items = self
            .ui_plugins
            .iter()
            .map(|plugin| PickerItem {
                id: plugin.id.clone(),
                label: plugin.label.clone(),
                meta: format!("{} · {}", plugin.source, plugin.status),
                provider: None,
            })
            .collect();
        let sel = self
            .ui_plugins
            .iter()
            .position(|plugin| plugin.status == "active")
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::UiPlugin,
            title: self
                .locale
                .tr(
                    " UI Plugins · enter apply · esc close ",
                    " UI 插件 · enter 应用 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    pub(crate) fn open_plugin_tree(&mut self) {
        let mut state = tui_tree_widget::TreeState::default();
        // Open every provider branch by default; the selection starts on the
        // first provider row. Identifiers are paths: [provider] for a branch
        // and [provider, entryId] for one plugin leaf.
        let mut first_provider: Option<String> = None;
        for plugin in &self.static_plugins {
            let provider = crate::app::plugin_provider(&plugin.module_name);
            state.open(vec![provider.clone()]);
            if first_provider.is_none() {
                first_provider = Some(provider);
            }
        }
        if let Some(provider) = first_provider {
            state.select(vec![provider]);
        }
        self.plugin_tree = Some(PluginTree {
            title: self
                .locale
                .tr(
                    " Host plugins · static · read only · ↑↓ ←→ navigate · esc close ",
                    " Host 插件 · 静态 · 只读 · ↑↓ ←→ 导航 · esc 关闭 ",
                )
                .into(),
            state,
        });
    }

    pub(crate) fn open_dynamic_plugin_picker(&mut self) {
        let items = self
            .dynamic_plugins
            .iter()
            .map(|plugin| PickerItem {
                id: plugin.id.clone(),
                label: plugin.name.clone(),
                meta: match plugin.status.as_str() {
                    "awaiting-approval" => "dynamic · awaiting approval · enter review".into(),
                    "running" | "waiting" => "dynamic · running · enter stop".into(),
                    "starting-host" | "client-pending" => "dynamic · starting".into(),
                    "failed" => "dynamic · failed · enter retry".into(),
                    _ => "dynamic · stopped · enter restore".into(),
                },
                provider: None,
            })
            .collect();
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::DynamicPlugin,
            title: self
                .locale
                .tr(
            " dynamic plugins · enter manage · esc close ",
            " 动态插件 · enter 管理 · esc 关闭 ",
                )
                .into(),
            sel: 0,
            items,
        });
    }

    pub(crate) fn open_plugin_approval_picker(&mut self, request_id: String) {
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::PluginApproval,
            title: self
                .locale
                .tr(
                    " plugin approval · enter decide ",
                    " 插件审批 · enter 决定 ",
                )
                .into(),
            sel: 0,
            items: vec![
                PickerItem {
                    id: "allow-version".into(),
                    label: self.locale.tr("Allow this version", "允许当前版本").into(),
                    meta: String::new(),
                    provider: Some(request_id.clone()),
                },
                PickerItem {
                    id: "allow-future".into(),
                    label: self
                        .locale
                        .tr("Allow future versions", "允许后续版本")
                        .into(),
                    meta: String::new(),
                    provider: Some(request_id.clone()),
                },
                PickerItem {
                    id: "reject".into(),
                    label: self.locale.tr("Reject", "拒绝").into(),
                    meta: String::new(),
                    provider: Some(request_id),
                },
            ],
        });
    }

    pub(crate) fn plugin_command_active(&self, name: &str) -> bool {
        self.plugin_commands
            .iter()
            .any(|command| command.name == name)
    }


    pub(crate) fn harness_switch_in_progress(&self) -> bool {
        matches!(self.state, RunState::Starting) && self.state_note == "switching Harness"
    }
}

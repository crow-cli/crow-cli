//! auth: App methods for the auth surface (Phase 2 split).

use super::*;
use crate::bus::Cmd;
use crate::controller::Controller;
use crate::transcript::NoticeLevel;

impl App {
    /// Take a pending Terminal Auth launch so the main loop can leave the TUI.
    pub fn take_terminal_auth(&mut self) -> Option<crate::acp_auth::TerminalAuthLaunch> {
        self.pending_terminal_auth.take()
    }

    pub(crate) fn open_auth_surface(&mut self, ctl: &Controller) {
        if self.demo {
            return;
        }
        if self.pending_terminal_auth.is_some() {
            return;
        }
        if matches!(self.picker.as_ref().map(|p| p.kind), Some(PickerKind::Auth)) {
            return;
        }
        self.state = RunState::Idle;
        self.run_started = None;
        self.state_note.clear();
        self.show_tip(self.locale.tr("sign-in needed — /auth to retry", "需要登录 —— /auth 重试"));
        self.start_auth("", ctl);
    }

    pub(crate) fn open_auth_picker(&mut self) {
        let items: Vec<PickerItem> = self
            .auth
            .methods
            .iter()
            .map(|method| PickerItem {
                id: method.id.clone(),
                label: method.name.clone().unwrap_or_else(|| method.id.clone()),
                meta: method.type_name.clone(),
                provider: None,
            })
            .collect();
        if items.is_empty() {
            return;
        }
        let current = self.auth.method_id.clone();
        let sel = current
            .as_ref()
            .and_then(|id| items.iter().position(|item| item.id == *id))
            .unwrap_or(0);
        self.picker = Some(Picker {
            offset: 0,
            kind: PickerKind::Auth,
            title: self
                .locale
                .tr(
                    " sign in · enter select · esc close ",
                    " 登录 · enter 选择 · esc 关闭 ",
                )
                .into(),
            sel,
            items,
        });
    }

    pub(crate) fn start_auth(&mut self, arg: &str, ctl: &Controller) {
        use crate::acp_auth::{
            authenticate_meta_from_method, select_auth_method, values_from_auth_arg,
        };
        if self.demo {
            self.transcript
                .push_notice(
                    NoticeLevel::Info,
                    self.locale
                        .tr("demo has no ACP authenticate", "演示模式没有 ACP authenticate")
                        .into(),
                );
            return;
        }
        if self.auth.status == crate::acp_auth::AuthStatus::SigningIn {
            self.show_tip(self.locale.tr("sign-in is still pending — waiting for the Agent", "登录仍在进行中，等待 Agent 返回结果"));
            return;
        }
        if self.auth.methods.is_empty() {
            self.transcript.push_notice(
                NoticeLevel::Warn,
                self.auth.message.clone().unwrap_or_else(|| {
                    self.locale
                        .tr(
                            "this agent did not advertise auth methods",
                            "此 Agent 未声明认证方式",
                        )
                        .into()
                }),
            );
            return;
        }
        let arg = arg.trim();
        if arg.is_empty() && self.auth.methods.len() > 1 {
            self.open_auth_picker();
            return;
        }
        let (method_id, rest) = {
            let mut parts = arg.splitn(2, char::is_whitespace);
            let first = parts.next().unwrap_or("");
            let rest = parts.next().unwrap_or("").trim();
            if self.auth.methods.iter().any(|m| m.id == first) {
                (first.to_string(), rest.to_string())
            } else {
                (
                    self.auth
                        .method_id
                        .clone()
                        .unwrap_or_else(|| self.auth.methods[0].id.clone()),
                    arg.to_string(),
                )
            }
        };
        let Some(method) = select_auth_method(&self.auth.methods, Some(&method_id)).cloned() else {
            self.transcript.push_notice(
                NoticeLevel::Warn,
                self.locale.trf(
                    "ACP auth method is unavailable or not supported: {}",
                    "ACP 认证方式不可用或不支持：{}",
                    &[method_id.clone()],
                ),
            );
            return;
        };
        if method.is_env_prompt() {
            let vars = method
                .vars
                .iter()
                .map(|v| v.name.as_str())
                .collect::<Vec<_>>()
                .join(", ");
            self.transcript.push_notice(
                NoticeLevel::Warn,
                if vars.is_empty() {
                    self.locale.trf(
                        "ACP auth method {} requires credential variables and cannot be started as a sign-in flow.",
                        "ACP 认证方式 {} 需要凭据变量，无法以登录流程启动。",
                        &[method.id.clone()],
                    )
                } else {
                    self.locale.trf(
                        "ACP auth method {} requires credential variables ({}) and cannot be started as a sign-in flow.",
                        "ACP 认证方式 {} 需要凭据变量（{}），无法以登录流程启动。",
                        &[method.id.clone(), vars],
                    )
                },
            );
            return;
        }
        let values = values_from_auth_arg(&method, &rest);
        if method.form && authenticate_meta_from_method(&method, &values).is_none() {
            self.show_tip(self.locale.tr(
                "usage: /auth <api-key> · gateway: /auth <base-url> <api-key>",
                "用法：/auth <api-key> · 网关：/auth <base-url> <api-key>",
            ));
            return;
        }
        if values.is_empty() {
            if let Some(launch) = method.terminal_launch.clone() {
                self.pending_terminal_auth = Some(launch);
                self.transcript.push_notice(
                    NoticeLevel::Info,
                    self.locale.trf(
                        "leaving the TUI for {} — return here when it finishes",
                        "离开 TUI 前往 {} —— 完成后回到这里",
                        &[method
                            .name
                            .as_deref()
                            .unwrap_or(&method.id)
                            .to_string()],
                    ),
                );
                return;
            }
        }
        self.auth.status = crate::acp_auth::AuthStatus::SigningIn;
        self.auth.method_id = Some(method.id.clone());
        self.auth.method_name = method.name.clone();
        self.auth.message = None;
        if self.view_overlay.as_ref().is_some_and(|view| view.id == "builtin.auth.failure") {
            self.view_overlay = None;
        }
        ctl.send(Cmd::Authenticate {
            method_id: method.id,
            values,
        });
    }
}

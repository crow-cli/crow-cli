//! Built-in TUI localization.
//!
//! ACP and plugin payloads remain authored by their owner. This module only
//! localizes client-owned chrome and built-in commands.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Locale {
    #[default]
    En,
    Zh,
}

impl Locale {
    pub fn parse(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "en" | "en-us" | "en_us" => Some(Self::En),
            "zh" | "zh-cn" | "zh_cn" | "cn" => Some(Self::Zh),
            _ => None,
        }
    }

    pub fn alternate(self) -> Self {
        match self {
            Self::En => Self::Zh,
            Self::Zh => Self::En,
        }
    }

    pub fn tr(self, en: &'static str, zh: &'static str) -> &'static str {
        match self {
            Self::En => en,
            Self::Zh => zh,
        }
    }

    /// Localized template with one `{}` placeholder (counts, sizes…).
    pub fn tr_fmt(self, en: &'static str, zh: &'static str, arg: usize) -> String {
        match self {
            Self::En => en.replace("{}", &arg.to_string()),
            Self::Zh => zh.replace("{}", &arg.to_string()),
        }
    }

    /// Localized template whose `{}` holes are filled left-to-right from
    /// `args` (string/`Display` values — use [`Self::tr_fmt`] for a lone
    /// `usize`). Unfilled holes stay literal, matching the static `tr` pair.
    pub fn trf(self, en: &'static str, zh: &'static str, args: &[String]) -> String {
        let mut out = match self {
            Self::En => en,
            Self::Zh => zh,
        }
        .to_string();
        for arg in args {
            if let Some(pos) = out.find("{}") {
                out.replace_range(pos..pos + 2, arg);
            }
        }
        out
    }

    pub fn command_desc(self, name: &str, fallback: &'static str) -> &'static str {
        if self == Self::En {
            return fallback;
        }
        match name {
            "help" => "显示帮助和使用提示",
            "keys" => "查看键盘快捷键",
            "new" => "开始一个新会话",
            "resume" => "列出最近 n 个会话（默认 50）· /resume <id> 恢复指定会话",
            "close" => "关闭当前会话标签页（最后一个标签页不能关闭）",
            "clear" => "清空对话滚动区",
            "model" => "通过 ACP 实时切换模型",
            "agent" => "切换 Agent 预设 · ctrl+shift+a",
            "effort" => "设置当前会话的推理强度",
            "permission" => "选择权限预设 · shift+tab 轮换",
            "plan" => "切换 Host 计划模式",
            "image" => "发送本地图片（png/jpeg/webp/gif）",
            "clip" => "附加剪贴板图片（macOS/Linux）",
            "harness" => "切换 Agent Harness —— 重启连接并开启新会话",
            "theme" => "切换明暗模式或主题包",
            "ui" => "切换 UI 插件",
            "vim" => "切换 vim 模式编辑（默认关闭）",
            "plugins" => "查看 Host 插件状态（只读）",
            "dynamic-plugins" => "查看或管理动态插件",
            "session" => "显示会话信息 · /session prev|next 切换标签页",
            "auth" => "ACP 登录（Backchat authenticate）",
            "lang" => "切换界面语言",
            "liang" => "召唤小难梁 — 🤫 空闲 · ⌨︎ 工作中",
            "quit" => "退出 crow",
            _ => fallback,
        }
    }

    /// Built-in Client Plugin command descriptions (`tuiCommands`), keyed by
    /// command name; unknown plugin commands keep their authored text.
    pub fn plugin_command_desc<'a>(self, name: &str, fallback: &'a str) -> &'a str {
        if self == Self::En {
            return fallback;
        }
        match name {
            "agents" => "切换 Agent 面板（on/off）",
            "status" => "显示会话运行状态与关键统计",
            "plan-view" => "打开当前 ACP 计划",
            "harness" => "立即切换 Harness 并启动新会话",
            _ => fallback,
        }
    }
}

fn default_ui_preset() -> String {
    "default".into()
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct UiSettings {
    pub language: Locale,
    #[serde(rename = "uiPreset")]
    pub ui_preset: String,
    /// Persisted light/dark mode (`dark` | `light`). Absent → the CLI
    /// `--theme` value, then the active pack's own preferred mode, then
    /// the builtin default (dark).
    #[serde(rename = "themeMode")]
    pub theme_mode: Option<String>,
    /// Persisted palette pack id (`default`, `catppuccin-macchiato`, …).
    /// Absent — or an id this binary does not carry, e.g. one a Plugin
    /// registered before it went away — falls back to `default`.
    pub theme: Option<String>,
    /// Persisted markdown body tone (`single` | `two`). Absent → the
    /// builtin default (`single`: CJK and Latin share the main `fg`).
    #[serde(rename = "markdownTone")]
    pub markdown_tone: Option<String>,
}

impl Default for UiSettings {
    fn default() -> Self {
        Self {
            language: Locale::default(),
            ui_preset: default_ui_preset(),
            theme_mode: None,
            theme: None,
            markdown_tone: None,
        }
    }
}

#[cfg(test)]
#[path = "../tests/unit/locale__tests.rs"]
mod tests;

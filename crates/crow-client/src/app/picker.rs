//! picker: extracted verbatim from src/app.rs (Phase 1 split).

use crate::transcript::Transcript;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum PickerKind {
    Model,
    Effort,
    Mode,
    Theme,
    UiPlugin,
    Permission,
    Session,
    Auth,
    CordisPlugin,
    CordisApproval,
    AgentHistory,
    Harness,
}

#[derive(Clone)]
pub struct PickerItem {
    pub id: String,
    pub label: String,
    pub meta: String,
    pub provider: Option<String>,
}

/// Fixed display width of the picker label column — rows pad/truncate to
/// this so the meta column lines up (char-based padding would misalign
/// CJK labels).
pub(crate) const PICKER_LABEL_COL: usize = 30;

/// One `/` menu entry: a builtin [`SlashCommand`] or a host skill (plugin
/// mode). Builtins win a name collision — the command namespace is closed
/// and resolved client-side before a line ever becomes a prompt; skill
/// lines ship as prompts the host expands.
#[derive(Clone)]
pub struct SlashEntry {
    pub disabled: bool,
    pub name: String,
    pub usage: String,
    pub desc: String,
    pub skill: bool,
    pub plugin: bool,
    /// Visual group for argument candidates. The group label is rendered on
    /// its first option without adding a selectable separator row.
    pub section: Option<String>,
    /// Full composer text for an argument candidate. Command-name rows leave
    /// this empty and retain the historical `/name ` tab completion.
    pub completion: Option<String>,
}

#[derive(Clone, serde::Deserialize)]
pub(crate) struct PluginCommand {
    pub(crate) name: String,
    pub(crate) description: String,
    #[serde(default)]
    pub(crate) input: Option<PluginCommandInput>,
}

#[derive(Clone, serde::Deserialize)]
pub(crate) struct PluginCommandInput {
    pub(crate) hint: String,
    #[serde(default)]
    pub(crate) options: Vec<PluginCommandOption>,
}

#[derive(Clone, serde::Deserialize)]
pub(crate) struct PluginCommandOption {
    #[serde(default)]
    pub(crate) disabled: bool,
    pub(crate) value: String,
    #[serde(default)]
    pub(crate) label: Option<String>,
    #[serde(default)]
    pub(crate) description: Option<String>,
}

#[derive(serde::Deserialize)]
pub(crate) struct PluginCommandCatalog {
    pub(crate) protocol: u64,
    pub(crate) commands: Vec<PluginCommand>,
}

#[derive(serde::Deserialize)]
pub(crate) struct PluginOverlaySnapshot {
    pub(crate) protocol: u64,
    pub(crate) overlay: Option<PluginOverlay>,
}

#[derive(serde::Deserialize)]
pub(crate) struct CordisApprovalsSnapshot {
    pub(crate) protocol: u64,
    pub(crate) approvals: Vec<crate::bus::PendingCordisApproval>,
}

#[derive(serde::Deserialize)]
pub(crate) struct UiPluginCatalog {
    pub(crate) protocol: u64,
    pub(crate) plugins: Vec<crate::bus::UiPluginItem>,
}

#[derive(serde::Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub(crate) enum PluginOverlay {
    Slider(SliderOverlay),
    Select(SelectOverlay),
    View(ViewOverlay),
}

#[derive(Clone, serde::Deserialize)]
pub struct SelectOverlay {
    pub id: String,
    pub title: String,
    pub value: String,
    pub options: Vec<SelectOption>,
    #[serde(default)]
    pub searchable: bool,
    #[serde(skip)]
    pub query: String,
    #[serde(skip)]
    pub sel: usize,
}

impl SelectOverlay {
    pub fn visible_indices(&self) -> Vec<usize> {
        let query = self.query.to_lowercase();
        let terms: Vec<_> = query.split_whitespace().collect();
        self.options.iter().enumerate().filter_map(|(index, option)| {
            let text = format!("{} {} {}", option.value, option.label,
                option.description.as_deref().unwrap_or("")).to_lowercase();
            (!self.searchable || terms.iter().all(|term| text.contains(*term))).then_some(index)
        }).collect()
    }

    pub(crate) fn reconcile_search(&mut self) {
        let visible = self.visible_indices();
        if !visible.contains(&self.sel) {
            if let Some(&first) = visible.first() { self.sel = first; }
        }
        if let Some(option) = self.options.get(self.sel) {
            self.value = option.value.clone();
        }
    }
}

#[derive(Clone, serde::Deserialize)]
pub struct SelectOption {
    #[serde(default)]
    pub disabled: bool,
    #[serde(default)]
    pub deletable: bool,
    pub value: String,
    pub label: String,
    #[serde(default)]
    pub description: Option<String>,
    /// Decorative section label; never contributes an option index or value.
    #[serde(default)]
    pub group: Option<String>,
}

pub(crate) fn select_initial_index(select: &SelectOverlay) -> Option<usize> {
    if select.id.is_empty() || select.title.is_empty() || select.options.is_empty() {
        return None;
    }
    let mut values = std::collections::HashSet::new();
    for option in &select.options {
        if option.value.is_empty()
            || option.label.is_empty()
            || option.group.as_ref().is_some_and(|group| group.trim().is_empty()
                || group.chars().any(|ch| ch.is_control() || matches!(ch, '\u{2028}' | '\u{2029}')))
            || !values.insert(option.value.as_str())
        {
            return None;
        }
    }
    select
        .options
        .iter()
        .position(|option| option.value == select.value)
}

#[derive(Clone, serde::Deserialize)]
pub struct SliderOverlay {
    pub id: String,
    pub title: String,
    pub min: f64,
    pub max: f64,
    pub step: f64,
    #[serde(default)]
    pub marks: Vec<SliderMark>,
    #[serde(rename = "snapToMarks", default)]
    pub snap_to_marks: bool,
    pub value: f64,
}

#[derive(Clone, serde::Deserialize)]
pub struct SliderMark {
    pub value: f64,
    /// Optional host-side mark identity. Parsed for protocol compatibility;
    /// the client renders by value/label and reports the numeric value back,
    /// so the id is not consumed client-side yet.
    #[serde(default)]
    #[allow(dead_code)]
    pub id: Option<String>,
    pub label: String,
}

#[derive(Clone, serde::Deserialize)]
pub struct ViewOverlay {
    pub id: String,
    pub title: String,
    pub nodes: Vec<crate::slots::TuiNode>,
    #[serde(skip)]
    pub scroll: usize,
    /// Plugin-owned views report submit/cancel over the compositor plane;
    /// builtin chrome such as `/keys` closes entirely inside the painter.
    #[serde(skip)]
    pub(crate) notify_plugin: bool,
}

pub struct Picker {
    pub kind: PickerKind,
    pub title: String,
    pub sel: usize,
    pub items: Vec<PickerItem>,
    /// First row of the popup's viewport. Unlike `sel` (which keys and the
    /// wheel move freely), the window only scrolls when the selection
    /// leaves it — the draw pass adjusts this by the minimum needed, so a
    /// static window lets ↑/↓ and wheel sweep the highlight row by row
    /// instead of re-pinning the window edge under it every frame.
    pub offset: usize,
}

/// The `/plugins` static inventory as a two-level tree (provider → plugin),
/// rendered by `ui::draw_plugin_tree` with the tui-tree-widget crate.
/// Items are rebuilt from `static_plugins` on every draw; the TreeState keeps
/// the selection and the opened provider branches stable across frames.
pub struct PluginTree {
    pub title: String,
    pub state: tui_tree_widget::TreeState<String>,
}

/// The provider bucket for one loader entry: the npm scope when the module
/// name carries one, otherwise a stable `core` bucket. This is the first
/// level of the `/plugins` tree.
pub fn plugin_provider(module: &str) -> String {
    module
        .split_once('/')
        .map(|(scope, _)| scope)
        .unwrap_or("core")
        .to_string()
}

/// The plugin name shown under its provider: the module name without its
/// provider scope (`foo/agent` → `agent`).
pub fn plugin_short_name(module: &str) -> String {
    module
        .split_once('/')
        .map(|(_, name)| name)
        .unwrap_or(module)
        .to_string()
}

pub struct SubagentView {
    pub id: String,
    pub parent: String,
    pub label: String,
    pub running: bool,
    pub failed: bool,
    pub transcript: Transcript,
}

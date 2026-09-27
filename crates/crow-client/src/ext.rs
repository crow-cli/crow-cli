//! The crow TUI extension contract shared by the native client surfaces.
//!
//! Two levels of method name, and the split is the old one with the vendor
//! segment dropped. `_crow/tui/*` is the extension family proper: the
//! compositor state an agent negotiates and the calls that answer it. One
//! method sits outside the family — `_crow/plugins/list`, the read-only
//! inventory of statically configured plugins — because it was never part of
//! the negotiated surface.
//!
//! Nothing implements this protocol yet, so the names are a contract crow
//! publishes, not one it inherited.

/// Version of the extension family this client speaks. Advertised in
/// `agentCapabilities._meta.crow.tui.protocol` and checked against the same
/// key on the agent's `initialize` result.
pub const PROTOCOL: u64 = 0;

pub const THEME_UPDATE: &str = "_crow/tui/theme/update";
pub const THEME_REMOVE: &str = "_crow/tui/theme/remove";
pub const THEME_SELECTED: &str = "_crow/tui/theme/selected";
pub const SLOTS_UPDATE: &str = "_crow/tui/slots/update";
pub const COMMANDS_UPDATE: &str = "_crow/tui/commands/update";
pub const COMMAND_INVOKE: &str = "_crow/tui/commands/invoke";
pub const OVERLAY_UPDATE: &str = "_crow/tui/overlay/update";
pub const OVERLAY_EVENT: &str = "_crow/tui/overlay/event";
pub const QUEUE_UPDATE: &str = "_crow/tui/queue/update";
pub const AGENTS_UPDATE: &str = "_crow/tui/agents/update";
pub const AGENTS_SELECT: &str = "_crow/tui/agents/select";
pub const AGENTS_NAVIGATE: &str = "_crow/tui/agents/navigate";
pub const SESSION_ACTIVE: &str = "_crow/tui/session/active";
pub const SESSION_CONFIG_SET: &str = "_crow/tui/session-config/set";
pub const APPROVALS_UPDATE: &str = "_crow/tui/approvals/update";
pub const APPROVAL_RESPOND: &str = "_crow/tui/approvals/respond";
pub const UI_UPDATE: &str = "_crow/tui/ui/update";
pub const UI_SELECTED: &str = "_crow/tui/ui/selected";

/// Read-only inventory of statically configured plugins. Outside the
/// extension family: it needs no negotiated capability.
pub const STATIC_PLUGINS_LIST: &str = "_crow/plugins/list";
/// The agent's own dynamic plugin registry, and the two calls that manage it.
pub const DYNAMIC_PLUGINS_LIST: &str = "_crow/tui/plugins/list";
pub const PLUGIN_START: &str = "_crow/tui/plugins/start";
pub const PLUGIN_STOP: &str = "_crow/tui/plugins/stop";

pub fn advertised_by_agent(initialize: &serde_json::Value) -> bool {
    initialize
        .get("agentCapabilities")
        .and_then(|capabilities| capabilities.get("_meta"))
        .and_then(|meta| meta.get("crow"))
        .and_then(|crow| crow.get("tui"))
        .and_then(|tui| tui.get("protocol"))
        .and_then(serde_json::Value::as_u64)
        == Some(PROTOCOL)
}

//! slash_catalog: extracted verbatim from src/app.rs (Phase 1 split).

use super::*;

pub struct SlashCommand {
    pub name: &'static str,
    pub usage: &'static str,
    pub desc: &'static str,
}

pub const SLASH_COMMANDS: &[SlashCommand] = &[
    SlashCommand {
        name: "agent",
        usage: "/agent [id]",
        desc: "switch agent preset · ctrl+shift+a",
    },
    SlashCommand {
        name: "auth",
        usage: "/auth [method|api-key]",
        desc: "ACP sign-in (Backchat authenticate)",
    },
    SlashCommand {
        name: "clear",
        usage: "/clear",
        desc: "clear the scrollback",
    },
    SlashCommand {
        name: "clip",
        usage: "/clip [text]",
        desc: "attach the clipboard image (macOS/Linux)",
    },
    SlashCommand {
        name: "close",
        usage: "/close",
        desc: "close the current session tab (last tab cannot close)",
    },
    // Parked, not deleted: `/dynamic-plugins` reaches a plugin host that does
    // not exist — no agent advertises `_crow/tui`, so the entry could only ever
    // answer "agent does not advertise _crow/tui". The machinery is intact and
    // still compiled: `Cmd::FetchDynamicPlugins` / `SetDynamicPluginEnabled` /
    // `RespondPluginApproval`, `ensure_agent_ext` and `fetch_dynamic_plugins` in
    // `acp.rs`, their handlers in `acp/control.rs`, `CtlEvent::DynamicPlugins`,
    // `DynamicPluginItem`, `PendingPluginApproval`, `App::dynamic_plugins` /
    // `pending_plugin_approvals`, `PickerKind::DynamicPlugin` /
    // `PluginApproval`, `open_dynamic_plugin_picker` /
    // `open_plugin_approval_picker`, `draw_plugin_approval`, the alt-key answer
    // in `keys_router.rs`, the `slash.rs` handler and the zh `command_desc` arm.
    // `run_slash("dynamic-plugins", "")` still resolves — see
    // `the_plugin_commands_are_parked_out_of_the_menu_but_the_machinery_still_runs`.
    // Re-registering is uncommenting this entry.
    // SlashCommand {
    //     name: "dynamic-plugins",
    //     usage: "/dynamic-plugins",
    //     desc: "review or manage the agent's dynamic plugins",
    // },
    SlashCommand {
        name: "effort",
        usage: "/effort [off|high|max]",
        desc: "reasoning effort for this session",
    },
    SlashCommand {
        name: "harness",
        usage: "/harness [id]",
        desc: "switch the agent harness — respawns the connection",
    },
    SlashCommand {
        name: "help",
        usage: "/help",
        desc: "show help and tips",
    },
    SlashCommand {
        name: "image",
        usage: "/image <path> [text]",
        desc: "send a local image (png/jpeg/webp/gif)",
    },
    SlashCommand {
        name: "keys",
        usage: "/keys",
        desc: "keyboard shortcuts",
    },
    SlashCommand {
        name: "lang",
        usage: "/lang [zh|en]",
        desc: "switch interface language",
    },
    // Parked, not deleted: `/liang` is a branded pet, and this is crow-cli's
    // harness. The machinery is intact and still compiled — `src/pet.rs`, the
    // sprites in `assets/pet/liang-{idle,working}.png`, the `App::pet_visible`
    // / `pet_pixels` / `pet_want` fields, the pet rect `ui.rs` hands to
    // `pet_want`, the `slash.rs` handler and its `on|off` argument completion,
    // and the zh `command_desc` arm in `locale.rs`. `run_slash("liang", …)`
    // still resolves, which is what `pet__tests.rs` and
    // `liang_toggle_is_transient_and_keeps_the_empty_welcome_centered` drive.
    // The sprite and kitty-graphics plumbing is the expensive part; a crow pet
    // re-registers by uncommenting this entry and swapping the two PNGs.
    // SlashCommand {
    //     name: "liang",
    //     usage: "/liang [on|off]",
    //     desc: "召唤小难梁 — 🤫 idle · ⌨︎ working",
    // },
    SlashCommand {
        name: "model",
        usage: "/model [id]",
        desc: "switch model · live over ACP",
    },
    SlashCommand {
        name: "new",
        usage: "/new [id]",
        desc: "start a fresh session",
    },
    SlashCommand {
        name: "permission",
        usage: "/permission [preset]",
        desc: "permission preset picker · shift+tab cycles",
    },
    SlashCommand {
        name: "plan",
        usage: "/plan [on|off]",
        desc: "toggle host plan mode",
    },
    // Parked with `/dynamic-plugins` above, for the same reason: the read-only
    // Host inventory is served over `_crow/plugins/list`, which nothing
    // answers. Machinery intact and still compiled: `Cmd::FetchStaticPlugins`,
    // `fetch_static_plugins` and `static_plugins_from_value` in `acp.rs`, the
    // handler in `acp/control.rs`, `CtlEvent::StaticPlugins`,
    // `StaticPluginItem`, `App::static_plugins`, and the grouped render in
    // `ui.rs`. `run_slash("plugins", "")` still resolves.
    // SlashCommand {
    //     name: "plugins",
    //     usage: "/plugins",
    //     desc: "show Host plugin status (read-only)",
    // },
    SlashCommand {
        name: "quit",
        usage: "/quit",
        desc: "exit crow",
    },
    SlashCommand {
        name: "resume",
        usage: "/resume [n|id]",
        desc: "list the n most recent sessions (default 50) · /resume <id> resumes it",
    },
    SlashCommand {
        name: "session",
        usage: "/session [view|prev|next]",
        desc: "show session info · prev/next switch session tab",
    },
    SlashCommand {
        name: "theme",
        usage: "/theme [id|toggle]",
        desc: "switch Theme Plugin or toggle dark/light",
    },
    // Parked with the two plugin commands above: a UI Plugin is mounted by the
    // same host that does not exist. Machinery intact and still compiled:
    // `App::ui_plugins`, `UiPluginItem`, `open_ui_plugin_picker`,
    // `Cmd::PluginUiSelected`, the `_crow/tui/ui/update` + `ui/selected`
    // projection in `app/pump.rs` and `acp/control.rs`, the `"ui"` argument
    // completion arm and the `slash.rs` handler. `run_slash("ui", "")` still
    // resolves.
    // SlashCommand {
    //     name: "ui",
    //     usage: "/ui [id]",
    //     desc: "switch UI Plugin",
    // },
    SlashCommand {
        name: "vim",
        usage: "/vim [on|off]",
        desc: "toggle vim modal editing (default off)",
    },
];

/// Demo seeds for `/agent` when no agent catalog has arrived. Live ACP
/// replaces these with the extra composition select the agent advertised.
///
/// There used to be a fourth seed: a "Creator mode" whose whole description
/// was runtime inspection and preset authoring against the extension family.
/// It went with the three parked plugin commands, for the same reason — a menu
/// entry that can only answer "agent does not advertise `_crow/tui`" is worse
/// than no menu entry. An agent that really does author presets advertises its
/// own composition select; `stock_presets()` is only the demo's stand-in.
pub const AGENT_MODES: &[(&str, &str, &str)] = &[
    (
        "standard",
        "Standard mode",
        "full coding agent · files, shell, search, skills, subagents",
    ),
    (
        "code",
        "Code mode",
        "standard tools driven from one TypeScript program",
    ),
    (
        "minimal",
        "Minimal mode",
        "two tools · persistent bash + str_replace_editor",
    ),
];

/// The stock permission presets (id, one-line meaning). Shift+Tab cycles them;
/// `/permission <name>` passes any other id through for profiles with a
/// custom preset table (the host validates and lists what it knows).
pub const PERMISSION_PRESETS: &[(&str, &str)] = &[
    ("read-only", "read only — no file writes"),
    (
        "workspace-write",
        "write inside the workspace · wider actions ask for approval",
    ),
    (
        "danger-full-access",
        "full file access · approval prompts off — trusted dirs only",
    ),
];

/// Map common spellings onto the stock preset ids (`full` →
/// `danger-full-access`, `ws` → `workspace-write`, `ro` → `read-only`, …).
pub fn normalize_permission(arg: &str) -> Option<&'static str> {
    match arg.trim().to_ascii_lowercase().as_str() {
        "read-only" | "readonly" | "read" | "ro" => Some("read-only"),
        "workspace-write" | "workspace" | "write" | "ws" | "safe" | "sandbox" => {
            Some("workspace-write")
        }
        "danger-full-access" | "full-access" | "full" | "danger" | "yolo" => {
            Some("danger-full-access")
        }
        _ => None,
    }
}

/// User-facing permission label, mirroring the Web's `displayPermissionPreset`:
/// `danger-full-access` → "Full access"; kebab-case keys are title-cased.
pub fn permission_label(id: &str) -> String {
    if id == "danger-full-access" {
        return "Full access".to_string();
    }
    let kebab = !id.is_empty()
        && id.split('-').all(|seg| {
            !seg.is_empty()
                && seg
                    .chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        });
    if !kebab {
        return id.to_string();
    }
    id.split('-')
        .map(|seg| {
            let mut chars = seg.chars();
            match chars.next() {
                Some(f) => f.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub(crate) fn permission_picker_items(
    modes: &[crate::bus::CatalogPreset],
    reported: Option<&str>,
    current: &str,
) -> Vec<PickerItem> {
    modes
        .iter()
        .map(|p| {
            let mark = if reported == Some(p.id.as_str()) {
                " · current"
            } else if reported.is_none() && p.id == current {
                " · default"
            } else {
                ""
            };
            PickerItem {
                id: p.id.clone(),
                label: permission_label(&p.id),
                meta: format!("{}{mark}", p.description),
                provider: None,
            }
        })
        .collect()
}

/// The model picker's title. An empty list means the agent has not advertised a
/// catalog yet, and the title is the only place left that can say so.
pub(crate) fn model_picker_title(locale: crate::locale::Locale, empty: bool) -> &'static str {
    if empty {
        locale.tr(
            " model · waiting for the agent catalog ",
            " 模型 · 等待 Agent 上报目录 ",
        )
    } else {
        locale.tr(
            " model · enter select · esc close ",
            " 模型 · enter 选择 · esc 关闭 ",
        )
    }
}

/// The provider that serves `model` according to the agent's own catalog, when
/// exactly one entry carries that id. Two entries with the same id (one upstream
/// model behind two coding plans) stay ambiguous — only the user's pick can say
/// which one the session is on. The client never guesses a provider.
pub(crate) fn catalog_provider(
    models: &[crate::bus::CatalogModel],
    model: &str,
) -> Option<String> {
    if model.is_empty() {
        return None;
    }
    let mut matches = models.iter().filter(|entry| entry.id == model);
    let unique = matches.next()?;
    matches.next().is_none().then(|| unique.provider.clone())
}

/// Map a file extension to the attachment media type the host accepts.
pub(crate) fn media_type_for(path: &str) -> Option<&'static str> {
    let ext = path.rsplit('.').next()?.to_ascii_lowercase();
    match ext.as_str() {
        "png" => Some("image/png"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        "webp" => Some("image/webp"),
        "gif" => Some("image/gif"),
        _ => None,
    }
}

/// Read the raster image currently on the system clipboard as (bytes, media
/// type). Terminals don't deliver image paste over stdin, so this shells out
/// to the platform clipboard tool instead.
#[cfg(target_os = "macos")]
pub(crate) fn read_clipboard_image() -> Option<(Vec<u8>, &'static str)> {
    let tmp = std::env::temp_dir().join(format!("crow-clip-{}.png", std::process::id()));
    let tmp_s = tmp.to_str()?.to_string();
    let script = format!(
        "set out to \"{tmp_s}\"\n\
         set d to (the clipboard as «class PNGf»)\n\
         set h to open for access (POSIX file out) with write permission\n\
         write d to h as «class PNGf»\n\
         close access h\n\
         return out"
    );
    let out = std::process::Command::new("osascript")
        .arg("-e")
        .arg(&script)
        .output()
        .ok()?;
    if !out.status.success() {
        let _ = std::fs::remove_file(&tmp);
        return None;
    }
    let bytes = std::fs::read(&tmp).ok()?;
    let _ = std::fs::remove_file(&tmp);
    Some((bytes, "image/png"))
}

#[cfg(target_os = "linux")]
pub(crate) fn read_clipboard_image() -> Option<(Vec<u8>, &'static str)> {
    let attempts: &[(&str, &[&str])] = &[
        ("wl-paste", &["--type", "image/png"]),
        (
            "xclip",
            &["-selection", "clipboard", "-t", "image/png", "-o"],
        ),
    ];
    for (cmd, args) in attempts {
        if let Ok(out) = std::process::Command::new(cmd).args(*args).output() {
            if out.status.success() && !out.stdout.is_empty() {
                return Some((out.stdout, "image/png"));
            }
        }
    }
    None
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
pub(crate) fn read_clipboard_image() -> Option<(Vec<u8>, &'static str)> {
    None
}

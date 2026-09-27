//! App state and input handling — the grok-build interaction homage.
//!
//! Enter sends (or queues mid-turn, client-side); Ctrl+X steers the active
//! turn immediately; Esc cancels a running turn with the draft preserved, and
//! Esc owns interrupt; Ctrl+C clears a draft, then needs two empty presses to quit;
//! `!` runs a command in the session's local shell; `/` opens the slash menu; Up recalls
//! history on an empty prompt.

use std::collections::{HashMap, HashSet, VecDeque};
#[allow(unused_imports)]
use std::io::{BufReader, Read, Write};
#[cfg(not(unix))]
use std::io::BufRead;
use std::sync::mpsc::Sender;
use std::time::{Duration, Instant};

#[allow(unused_imports)]
use crossterm::event::{
    Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use unicode_width::UnicodeWidthChar;

#[allow(unused_imports)]
use crate::bus::{
    permission_ask_default_sel, AppEvent, Cmd, CtlEvent, PermissionAskOption, PermissionAskReply,
    SessionListItem,
};
// Only the `#[cfg(test)]` modules below name the type; the release build has
// no use for it, hence the gate instead of a bare import.
#[cfg(test)]
use crate::controller::Controller;
#[allow(unused_imports)]
use crate::events::parse_notification;
#[allow(unused_imports)]
use crate::input::{Action, VimMode};
#[allow(unused_imports)]
use crate::locale::{Locale, UiSettings};
use crate::markdown::ToneMode;
#[allow(unused_imports)]
use crate::runtime::{legacy_settings_paths, settings_path, RuntimeConfig};
use crate::theme::Theme;
#[allow(unused_imports)]
use crate::transcript::{clamp_str, NoticeLevel, Transcript};
mod ask_overlays;
mod keys;
mod picker;
mod session_slot;
mod settings_io;
mod shell;
mod slash_catalog;
mod staging;
mod selection;
mod lifecycle;
mod session_tabs;
mod theme;
mod harness;
mod slash;
mod send_queue;
mod pump;
mod mouse;
mod prefs;
mod keys_router;
mod at_menu;
mod dispatch;
mod asks;
mod pickers;
mod session_flow;
mod modes;
mod auth;
mod info;

pub use ask_overlays::*;
pub use keys::*;
pub use picker::*;
pub use session_slot::*;
use settings_io::*;
use shell::*;
pub use slash_catalog::*;
use staging::*;
pub use selection::*;
#[allow(unused_imports)]
pub use lifecycle::*;
#[allow(unused_imports)]
pub use session_tabs::*;
#[allow(unused_imports)]
pub use theme::*;
#[allow(unused_imports)]
pub use harness::*;
#[allow(unused_imports)]
pub use slash::*;
#[allow(unused_imports)]
pub use send_queue::*;
#[allow(unused_imports)]
pub use pump::*;
#[allow(unused_imports)]
pub use mouse::*;
#[allow(unused_imports)]
pub use prefs::*;
#[allow(unused_imports)]
pub use keys_router::*;
#[allow(unused_imports)]
pub use at_menu::*;
#[allow(unused_imports)]
pub use dispatch::*;
#[allow(unused_imports)]
pub use asks::*;
#[allow(unused_imports)]
pub use pickers::*;
#[allow(unused_imports)]
pub use session_flow::*;
#[allow(unused_imports)]
pub use modes::*;
#[allow(unused_imports)]
pub use auth::*;
pub use info::*;
pub const SPINNER: [char; 10] = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

const DOUBLE_CLICK_WINDOW: Duration = Duration::from_millis(400);
const CTRL_C_QUIT_WINDOW: Duration = Duration::from_millis(1500);



#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RunState {
    Idle,
    Starting,
    Running,
}

pub use crate::input::composer::ComposerEditor;





/// Folded per-session mode state (from the durable event stream — the same
/// facts the Web UI chips read). Only client preferences such as Agent preset
/// and effort survive across sessions; permission facts must come from the
/// current Host session.
#[derive(Default, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct Modes {
    pub plan: bool,
    pub sandbox: Option<String>,
    pub approval: Option<String>,
    pub permission: Option<String>,
    pub agent_preset: Option<String>,
    /// Reasoning effort as last requested from this client (`/effort`,
    /// the post-model-pick effort picker); the host doesn't echo one.
    pub effort: Option<String>,
}


pub struct App {
    pub theme: Theme,
    pub locale: Locale,
    /// Markdown body-color scheme: single (default, one color for CJK and
    /// Latin) or two-tone. A deliberately quiet preference — no command or
    /// picker surface; set `markdownTone` in settings.json (`two`) to opt in.
    pub tone_mode: ToneMode,
    pub palettes: Vec<crate::theme::PalettePack>,
    pub active_palette_id: String,
    /// Palette currently only *previewed* (dialog row or `/theme ` slash
    /// candidate under the highlight) but not yet confirmed with Enter,
    /// paired with the committed mode to put back once it is dropped: a
    /// pack that owns a mode previews in it, and that is not necessarily
    /// the mode in effect. Preview repaints `theme` without touching
    /// `active_palette_id`, so Esc or a moved highlight reverts to the
    /// committed theme.
    theme_preview: Option<(String, crate::theme::Mode)>,
    /// Palette confirmed with Enter whose Theme Plugin has not delivered
    /// its loaded palette yet. The preview colors stay on screen (no flash
    /// back to the old theme) until the palette arrival commits it.
    theme_pending: Option<String>,
    /// Persisted UI Preset id. The Client compositor owns activation; Rust
    /// keeps this only as a startup fallback before slot snapshots arrive.
    pub ui_preset: String,
    /// Latest compositor-private snapshots, keyed by declared Client slot.
    pub slot_snapshots: HashMap<String, crate::slots::SlotSnapshot>,
    pub transcript: Transcript,
    pub subagents: Vec<SubagentView>,
    current_subagents: HashSet<String>,
    next_subagent_starts_batch: bool,
    pub active_subagent: Option<String>,
    pub(crate) agent_selection: Option<String>,
    pub input: ComposerEditor,
    /// Optional vim modal editing (`/vim`); off by default.
    pub vim: crate::input::VimState,
    /// Display-cell width of the composer text well from the latest frame.
    pub(crate) composer_wrap_width: usize,
    /// Screen rect of the composer input well from the latest frame — mouse
    /// hit-testing (recorded by `ui::draw_input`).
    pub(crate) input_area: ratatui::layout::Rect,
    /// First text row shown inside the well (the viewport scroll from
    /// `ui::draw_input`).
    pub(crate) input_top: usize,
    /// Absolute screen cell of the soft caret from the latest frame (the
    /// reversed block `ui::draw` paints in the composer well or the
    /// elicitation field). `main` repositions the *hidden* hardware cursor
    /// onto this cell after every draw, so IME candidate popups anchor at
    /// the caret instead of wherever the frame diff left the cursor;
    /// `None` when no caret was painted this frame.
    pub caret_cell: Option<(u16, u16)>,
    /// Ordered char-index range selected in the composer: drag-select and
    /// copy highlight, `None` when no input selection is shown.
    pub(crate) input_sel: Option<InputSel>,
    /// A left-button drag inside the composer well is in progress.
    input_selecting: bool,
    /// Mouse pointer cell from the latest `Moved` event. The composer
    /// expand button is hover-revealed only while the pointer sits on it
    /// (issue #92 — mouse-only affordance, no key binding).
    pub(crate) mouse_pos: Option<(u16, u16)>,
    /// Composer well enlarged by the mouse-only expand button (issue #92):
    /// `true` pins the well to the amplified height, `false` restores the
    /// draft-following auto height.
    pub(crate) input_expanded: bool,
    /// Screen rect of the mouse-only expand/collapse button from the
    /// latest frame — it sits on the composer card's top-right border.
    /// Recorded every frame, even before the pointer finds it.
    pub(crate) expand_btn: Option<ratatui::layout::Rect>,
    /// True while the pointer rests on the expand button; only then does
    /// the frame painter show it (`needs_redraw` on change).
    pub(crate) hover_expand_btn: bool,
    /// Screen rect of the mouse-only `↥` user-prompt jump button (issue
    /// #103) from the latest frame — one cell left of the expand glyph on
    /// the composer card's top-right.
    pub(crate) prompt_jump_btn: Option<ratatui::layout::Rect>,
    /// True while the pointer rests on the `↥` button (`needs_redraw` on
    /// change, same hover policy as the expand button).
    pub(crate) hover_prompt_jump_btn: bool,
    /// Transcript cell of the user prompt the last `↥` click jumped to
    /// (issue #103). The next click walks one prompt back; the oldest
    /// wraps to the newest. In-memory only — never persisted.
    pub(crate) prompt_jump_cell: Option<usize>,
    /// The `↥` jump flash (issue #103): the transcript cell of the prompt
    /// that was just jumped to, with the instant the highlight (chip
    /// background wash + brand text) expires, 5 s after the click.
    /// `App::tick` clears it on expiry; the painter resolves the cell to
    /// lines per frame.
    pub(crate) prompt_flash: Option<(usize, std::time::Instant)>,
    /// Per-frame absolute line span `[start, end)` of the flashing prompt,
    /// resolved by `draw_chat` from `prompt_flash` against the current
    /// layout (streaming can move the prompt's lines). `None` when nothing
    /// flashes this frame.
    pub(crate) prompt_flash_lines: Option<(usize, usize)>,
    pub state: RunState,
    pub state_note: String,
    /// Welcome banner (whale + wordmark) — shown until the first real prompt.
    pub show_banner: bool,
    /// Pixel-art Liang at the composer's right edge (`/liang` toggles him).
    /// Off by default — `/liang on` summons him.
    pub pet_visible: bool,
    /// True when the terminal speaks the kitty graphics protocol: image
    /// thumbnails and the background layer emit real pixels (set by `main`).
    pub pet_pixels: bool,
    pub harness_badge: Option<crate::harness_badge::Badge>,
    pub harness_thumb: Option<ThumbPlacement>,
    /// The pet sprite the frame just drew around: cell box + working flag.
    /// Filled by `ui::draw` (the layout math lives there — one source of
    /// truth), reconciled against the terminal by `main` after the frame.
    pub pet_want: Option<(ratatui::layout::Rect, bool)>,
    /// Current git branch of the workspace, shown after the project path in
    /// the composer cap when git is available and the terminal is wide
    /// enough. Seeded at startup, then re-checked on a throttled tick and
    /// right after each session shell command (`None` otherwise).
    pub git_branch: Option<String>,
    /// Last time the workspace git branch was re-checked (tick throttle).
    git_check_at: Instant,
    pub run_started: Option<Instant>,
    pub spinner_idx: usize,
    pub scroll_up: usize, // lines above the bottom; 0 = follow
    /// Mouse selection over the chat pane (drag-to-select, copy on release).
    pub sel: Option<Selection>,
    /// A left-button drag is in progress.
    selecting: bool,
    last_click: Option<(Instant, u16, u16)>,
    /// Filled by `ui::draw_chat` every frame.
    pub chat_view: ChatView,
    /// Sessions offered by the open `/resume` picker (id → file lookup).
    resume_candidates: Vec<crate::sessions::SessionSummary>,
    /// `/resume` picker rows came from ACP `session/list` (pick → resume/load).
    resume_via_acp: bool,
    /// Agent advertised `loadSession`.
    load_session: bool,
    /// Agent advertised `sessionCapabilities.list` (or legacy `loadSession`).
    list_session: bool,
    /// Agent advertised `sessionCapabilities.resume`.
    resume_session_cap: bool,
    /// Last ACP `session_info_update` title.
    session_title: Option<String>,
    pub slash_sel: usize,
    /// Open `@file` browser menu (grammar + ratatui-explorer in `file_ref`).
    pub file_menu: Option<crate::file_ref::FileMenu>,
    /// Esc-dismissed `@` token tag (see `file_ref::token_tag`): an
    /// unchanged token must not reopen the browser. Survives menu
    /// rebuilds, so it lives on the App, not in `file_menu`.
    pub file_menu_dismissed: Option<String>,
    pub picker: Option<Picker>,
    /// Rows the open picker actually shows (`h - border`), recorded by
    /// `ui::draw_model_picker` — the page size for picker PageUp/PageDown.
    pub picker_page_rows: usize,
    /// ACP tool permission ask (separate from `/permission` session modes).
    pub permission_ask: Option<PermissionAskOverlay>,
    /// Standard ACP form elicitation, above permission and picker overlays.
    pub elicitation_ask: Option<ElicitationAskOverlay>,
    /// Client Plugin modal rendered and driven by the native compositor.
    pub slider_overlay: Option<SliderOverlay>,
    /// Client Plugin single-select form rendered by the native compositor.
    pub select_overlay: Option<SelectOverlay>,
    /// Read-only modal rendered from a semantic TuiNode tree. Client Plugins
    /// and builtin chrome such as `/keys` share this surface.
    pub view_overlay: Option<ViewOverlay>,
    /// Provider-grouped static plugin inventory (`/plugins`): a tui-tree-widget
    /// popup rebuilt from `static_plugins` every draw, selection/open state
    /// kept by the widget's own TreeState.
    pub plugin_tree: Option<PluginTree>,
    /// Rows the open plugin tree actually shows (`h - border`), recorded by
    /// `ui::draw_plugin_tree` — the page size for PageUp/PageDown.
    pub plugin_tree_page_rows: usize,
    /// Images staged in the composer as inline `[image N]` chips living in
    /// the draft text; editing a token away un-stages its image.
    pub pending_images: crate::attachments::Staged,
    /// Screen rects of the inline chips this frame (hover/cursor preview
    /// hit-testing; recorded by `ui::draw_input`).
    pub att_chips: Vec<(ratatui::layout::Rect, usize)>,
    /// Clickable semantic actions contributed by the current slot frame.
    pub(crate) slot_actions: Vec<(ratatui::layout::Rect, crate::slots::TuiAction)>,
    /// Kitty-graphics placement for the hover-preview popup this frame.
    pub att_thumbs: Vec<ThumbPlacement>,
    /// Chip index under the mouse pointer (grok-style hover preview).
    pub hover_att: Option<usize>,
    pub modes: Modes,
    /// User-invocable host skills (`available_commands_update`); merged into
    /// the slash menu after the builtins.
    pub skills: Vec<crate::bus::SkillInfo>,
    /// Client Plugin commands are compositor-private and live exactly as long
    /// as their owning Plugin Fiber.
    plugin_commands: Vec<PluginCommand>,
    /// Last Host Loader inventory (`/plugins`).
    pub(crate) static_plugins: Vec<crate::bus::StaticPluginItem>,
    /// Last backend-owned dynamic plugin inventory (`/cordis-plugins`).
    cordis_plugins: Vec<crate::bus::CordisPluginItem>,
    /// Model-requested dynamic activations awaiting a decision.
    pub(crate) pending_cordis_approvals: Vec<crate::bus::PendingCordisApproval>,
    /// ACP-carried UI Plugin catalog (`/ui`).
    ui_plugins: Vec<crate::bus::UiPluginItem>,
    /// Last advertised composition select (`/agent`).
    last_presets: Vec<crate::bus::CatalogPreset>,
    /// Last advertised ACP model select (`/model`).
    last_models: Vec<crate::bus::CatalogModel>,
    /// Last advertised session modes (`/permission`, shift+tab).
    permission_choices: Vec<crate::bus::CatalogPreset>,
    /// Last advertised effort catalog for the current model.
    effort_choices: Vec<String>,
    pub tip: Option<(String, Instant)>,
    /// CROW_KEYDEBUG=1: echo every delivered key event in the tip row.
    key_debug: bool,
    ctrl_c_armed: Option<CtrlCQuitChord>,
    pub session_id: String,
    /// Parked sessions — every session except the viewed one (issue #94).
    /// Conceptual tab order is this list with the live session spliced in
    /// at `current`; the App's own fields above always mirror the live tab.
    parked: Vec<SessionSlot>,
    /// Tab index of the live session (`0..=parked.len()`).
    current: usize,
    /// One FIFO entry for a tab awaiting its `SessionBound`: `/new`
    /// placeholders and `session/load` targets. The bind lands on the tab
    /// that asked, even if the user switched away while it resolved.
    /// Closing the tab before the bind resolves keeps the entry (its FIFO
    /// position still owns the in-flight request) but marks it dead — the
    /// bind is discarded when it arrives instead of rebinding some other
    /// tab.
    awaiting_binds: VecDeque<AwaitingBind>,
    /// Tab strip hit-test rects, recorded by `ui::draw_session_tabs`.
    pub(crate) tab_rects: Vec<(ratatui::layout::Rect, usize)>,
    /// First tab index rendered in the session tab strip (the strip's
    /// scroll window). Mouse clicks on the window's edge tabs nudge it by
    /// one so the neighboring tab appears — a mouse can walk through every
    /// session tab without ever hitting a dead end. The draw pass keeps the
    /// window sane (never past the tail, head-anchored when there is no
    /// overflow, live tab always in view).
    pub(crate) tab_strip_offset: usize,
    pub cfg: RuntimeConfig,
    /// Model explicitly picked this session (`/model`); wins over
    /// `transcript.last_model` in the chip until a turn realizes it.
    pub selected_model: Option<String>,
    /// Current model reported by this ACP session's config snapshot.
    pub session_model: Option<String>,
    /// `--model` for this run; consumed by the first session bind.
    pub startup_model: Option<String>,
    pub demo: bool,
    /// A live ACP agent owns runtime, credentials, and its advertised catalog.
    pub attached: bool,
    /// A real `session/new`, `session/resume`, or `session/load` supplied this id.
    /// Cached session options stay hidden until this becomes true.
    pub session_bound: bool,
    /// The unrequested startup/reconnect bind has been seen. Before it,
    /// any `SessionBound` is the acp-side `session/new` this client did not
    /// ask for — so when one arrives while tabs are awaiting their own
    /// binds it must land on the parked tab that is not awaiting anything,
    /// not on the FIFO head (issue #94 startup race). Seeded bound
    /// sessions (demo, tests) have no pending unrequested bind.
    startup_bound: bool,
    /// ACP initialize / authenticate status (live ACP only).
    pub auth: crate::acp_auth::AuthSnapshot,
    /// Leave the TUI and run this agent login, then `authenticate`.
    pending_terminal_auth: Option<crate::acp_auth::TerminalAuthLaunch>,
    pub quit: bool,
    /// Escape suppresses slash recommendations for the current draft without
    /// deleting it. Text edits or an explicit Tab completion reopen them.
    slash_completion_dismissed: bool,
    pub queued: usize,
    /// Follow-ups not yet sent over ACP. The Agent only sees the front item
    /// after the active turn settles.
    prompt_queue: VecDeque<ClientQueuedPrompt>,
    queue_selection: Option<usize>,
    queue_edit: Option<QueueEditState>,
    /// Send Now bubbles awaiting the concurrent ACP request result.
    pending_steer_cells: HashMap<u64, PendingSteer>,
    next_prompt_id: u64,
    /// A first prompt was handed to the controller but has not reached the
    /// ACP request task yet. Runtime startup alone does not make a turn busy.
    prompt_pending: bool,
    shell_seq: u64,
    shell_pending: Vec<(u64, String, usize, u64)>, // (id, session id, cell idx, transcript gen)
    shell_worker: Option<ShellWorker>,
    bus_tx: Sender<AppEvent>,
    pub server_info: Option<String>,
    /// Badge tag of the protocol this connection negotiated — `acp` or `acp2`.
    /// Connection-scoped, not session-scoped: one negotiated connection serves
    /// every tab, so it is deliberately NOT parked in `SessionConnection` (a
    /// tab parked before a `/harness` switch would restore a stale tag).
    /// `None` until `initialize` returns, and for the demo/legacy paths that
    /// never negotiate.
    pub protocol_tag: Option<&'static str>,
    pub connection_error: Option<String>,
    pub needs_redraw: bool,
}


impl App {
    pub fn active_background(&self) -> Option<&crate::theme::ThemeBackground> {
        self.palettes
            .iter()
            .find(|pack| pack.id == self.active_palette_id && pack.loaded)
            .and_then(|pack| pack.background.as_ref())
    }

    pub fn canvas_background_color(&self) -> ratatui::style::Color {
        if self.pet_pixels && self.active_background().is_some() {
            ratatui::style::Color::Reset
        } else {
            self.theme.bg
        }
    }

    pub fn new(
        theme: Option<Theme>,
        cfg: RuntimeConfig,
        session_id: String,
        demo: bool,
        attached: bool,
        bus_tx: Sender<AppEvent>,
    ) -> Self {
        let palettes = crate::theme::PalettePack::builtin_packs();
        let settings = Self::load_settings(&cfg);
        // The persisted pack id. An id this binary does not carry — a Plugin
        // pack from an older install — falls back to the builtin default.
        let active_palette_id = settings
            .theme
            .as_deref()
            .filter(|id| palettes.iter().any(|pack| pack.id == **id))
            .unwrap_or("default")
            .to_string();
        let active = palettes
            .iter()
            .find(|pack| pack.id == active_palette_id)
            .expect("`default` is always a builtin pack");
        // Explicit `--theme` on the CLI wins; otherwise the persisted
        // light/dark mode; otherwise the pack's own preferred mode (Latte is
        // a light theme); otherwise the builtin default (dark).
        let mode = theme
            .as_ref()
            .map(|t| t.mode)
            .or_else(|| settings.theme_mode.as_deref().and_then(crate::theme::Mode::parse))
            .or(active.preferred_mode)
            .unwrap_or(crate::theme::Mode::Dark);
        let theme = active.theme(mode);
        let locale = settings.language;
        // Persisted markdown body tone (`single` | `two`); absent → single.
        let tone_mode = settings
            .markdown_tone
            .as_deref()
            .and_then(ToneMode::parse)
            .unwrap_or_default();
        let mut app = App {
            theme,
            locale,
            tone_mode,
            palettes,
            active_palette_id,
            theme_preview: None,
            theme_pending: None,
            ui_preset: settings.ui_preset,
            slot_snapshots: HashMap::new(),
            transcript: Transcript::new(session_id.clone()),
            subagents: Vec::new(),
            current_subagents: HashSet::new(),
            next_subagent_starts_batch: true,
            active_subagent: None,
            agent_selection: None,
            input: ComposerEditor::new(),
            vim: crate::input::VimState::default(),
            composer_wrap_width: 80,
            input_area: ratatui::layout::Rect::default(),
            input_top: 0,
            caret_cell: None,
            input_sel: None,
            input_selecting: false,
            mouse_pos: None,
            input_expanded: false,
            expand_btn: None,
            hover_expand_btn: false,
            prompt_jump_btn: None,
            hover_prompt_jump_btn: false,
            prompt_jump_cell: None,
            prompt_flash: None,
            prompt_flash_lines: None,
            state: RunState::Idle,
            state_note: String::new(),
            show_banner: true,
            pet_visible: false,
            pet_pixels: false,
            harness_badge: None,
            harness_thumb: None,
            pet_want: None,
            git_branch: None,
            git_check_at: Instant::now(),
            run_started: None,
            spinner_idx: 0,
            scroll_up: 0,
            sel: None,
            selecting: false,
            last_click: None,
            chat_view: ChatView::default(),
            resume_candidates: Vec::new(),
            resume_via_acp: false,
            load_session: false,
            list_session: false,
            resume_session_cap: false,
            session_title: None,
            slash_sel: 0,
            file_menu: None,
            file_menu_dismissed: None,
            picker: None,
            picker_page_rows: 0,
            permission_ask: None,
            elicitation_ask: None,
            slider_overlay: None,
            select_overlay: None,
            view_overlay: None,
            plugin_tree: None,
            plugin_tree_page_rows: 0,
            pending_images: crate::attachments::Staged::default(),
            att_chips: Vec::new(),
            slot_actions: Vec::new(),
            att_thumbs: Vec::new(),
            hover_att: None,
            modes: Modes::default(),
            skills: Vec::new(),
            plugin_commands: Vec::new(),
            static_plugins: Vec::new(),
            cordis_plugins: Vec::new(),
            pending_cordis_approvals: Vec::new(),
            ui_plugins: Vec::new(),
            last_presets: Vec::new(),
            last_models: Vec::new(),
            permission_choices: Vec::new(),
            effort_choices: Vec::new(),
            tip: None,
            key_debug: std::env::var("CROW_KEYDEBUG").is_ok_and(|v| v == "1"),
            ctrl_c_armed: None,
            session_id,
            parked: Vec::new(),
            current: 0,
            awaiting_binds: VecDeque::new(),
            tab_rects: Vec::new(),
            tab_strip_offset: 0,
            cfg,
            selected_model: None,
            session_model: None,
            startup_model: None,
            demo,
            attached,
            session_bound: demo,
            // Seeded-bound sessions (demo, tests, local resume) have no
            // unrequested bind coming; a live ACP start does.
            startup_bound: demo,
            auth: crate::acp_auth::AuthSnapshot::none(),
            pending_terminal_auth: None,
            quit: false,
            slash_completion_dismissed: false,
            queued: 0,
            prompt_queue: VecDeque::new(),
            queue_selection: None,
            queue_edit: None,
            pending_steer_cells: HashMap::new(),
            next_prompt_id: 1,
            prompt_pending: false,
            shell_seq: 0,
            shell_pending: Vec::new(),
            shell_worker: None,
            bus_tx,
            server_info: None,
            protocol_tag: None,
            connection_error: None,
            needs_redraw: true,
        };
        app.transcript.locale = locale;
        app
    }
}



#[cfg(test)]
#[path = "../tests/unit/app__persistent_shell_tests.rs"]
mod persistent_shell_tests;

pub fn timestamp() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};
    static COUNTER: AtomicU64 = AtomicU64::new(1);
    let micros = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros())
        .unwrap_or(0);
    let seq = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{micros:x}-{seq:x}")
}

/// Slice `s` by display-cell range `[c0, c1)`: a char is included when its
/// cell span overlaps the range (so a double-width char straddling the
/// boundary is kept — matching what the highlight visually covers).
pub(crate) fn slice_by_cells(s: &str, c0: usize, c1: usize) -> String {
    let mut out = String::new();
    let mut w = 0usize;
    for ch in s.chars() {
        let cw = ch.width().unwrap_or(0).max(1);
        if w + cw > c0 && w < c1 {
            out.push(ch);
        }
        w += cw;
        if w >= c1 {
            break;
        }
    }
    out
}

/// The whitespace-delimited word covering display column `col` of `line`:
/// `(start_col, cell_width, word)`. `None` on whitespace or past the end.
pub(crate) fn word_span(line: &str, col: usize) -> Option<(usize, usize, String)> {
    let cw = |ch: char| ch.width().unwrap_or(0).max(1);
    let chars: Vec<char> = line.chars().collect();
    let mut w = 0usize;
    let mut hit = None;
    for (i, ch) in chars.iter().enumerate() {
        if col < w + cw(*ch) {
            hit = Some(i);
            break;
        }
        w += cw(*ch);
    }
    let i = hit?;
    if chars[i].is_whitespace() {
        return None;
    }
    let (mut a, mut b) = (i, i);
    while a > 0 && !chars[a - 1].is_whitespace() {
        a -= 1;
    }
    while b + 1 < chars.len() && !chars[b + 1].is_whitespace() {
        b += 1;
    }
    let start_col: usize = chars[..a].iter().copied().map(cw).sum();
    let width: usize = chars[a..=b].iter().copied().map(cw).sum();
    Some((start_col, width, chars[a..=b].iter().collect()))
}

#[cfg(test)]
#[path = "../tests/unit/app__resume_tests.rs"]
mod resume_tests;

#[cfg(test)]
#[path = "../tests/unit/app__session_tabs_tests.rs"]
mod session_tabs_tests;

#[cfg(test)]
#[path = "../tests/unit/app__selection_tests.rs"]
mod selection_tests;

#[cfg(test)]
#[path = "../tests/unit/app__mode_tests.rs"]
mod mode_tests;

#[cfg(test)]
#[path = "../tests/unit/app__palette_tests.rs"]
mod palette_tests;

#[cfg(test)]
#[path = "../tests/unit/app__right_slot_tests.rs"]
mod right_slot_tests;

#[cfg(test)]
#[path = "../tests/unit/app__scroll_tests.rs"]
mod scroll_tests;

#[cfg(test)]
#[path = "../tests/unit/app__harness_tests.rs"]
mod harness_tests;

#[cfg(test)]
#[path = "../tests/unit/app__at_menu_tests.rs"]
mod at_menu_tests;

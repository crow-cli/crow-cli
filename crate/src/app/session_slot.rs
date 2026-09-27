//! session_slot: extracted verbatim from src/app.rs (Phase 1 split).

use super::*;
use std::collections::{HashMap, HashSet, VecDeque};
use std::time::Instant;
use crate::transcript::Transcript;

/// One non-live session's full state while another tab is viewed (issue
/// #94). The App's own fields always describe the viewed session; a tab
/// switch moves them into a slot and loads the target slot in their place.
///
/// Everything the frame paints between the session tab strip and the
/// composer stats dock is session state: the transcript and its scroll
/// position, the composer draft + staged images + `@file` browser, the
/// queue shelf, subagents, ACP asks, painter popups — a tab switch must
/// never show another session's chrome on this session's tab.
pub struct SessionSlot {
    pub id: String,
    pub connection: Option<crate::bus::SessionConnection>,
    pub title: Option<String>,
    pub transcript: Transcript,
    /// Composer draft (text, cursor, per-tab recall history) rides with
    /// its session like the queue does — the composer area is bound to
    /// the viewed tab.
    pub input: ComposerEditor,
    /// Images staged in the draft as `[image n]` chips (draft-bound).
    pub pending_images: crate::attachments::Staged,
    /// Composer well pinned to the amplified height (issue #92).
    pub input_expanded: bool,
    /// Open `@file` browser + its Esc-dismissed `@` token tag. Both are
    /// draft-bound: the menu filters the draft's token, so it follows the
    /// draft to its tab.
    pub file_menu: Option<crate::file_ref::FileMenu>,
    pub file_menu_dismissed: Option<String>,
    /// Chat scroll offset in lines above the bottom (0 = follow).
    pub scroll_up: usize,
    /// Model explicitly picked on this session (`/model`); wins over
    /// `transcript.last_model` in the chip until a turn realizes it.
    pub selected_model: Option<String>,
    pub session_model: Option<String>,
    /// Welcome banner: shown until this session sends its first prompt.
    pub show_banner: bool,
    /// Meta-row chrome while the session runs: state note text and the
    /// elapsed-timer anchor.
    pub state_note: String,
    pub run_started: Option<Instant>,
    /// Authoritative per-session running bit (folded from `SessionStatus`
    /// and turn lifecycle events).
    pub running: bool,
    /// Finished while parked → tab badge until the user views the tab.
    pub completed_unseen: bool,
    pub prompt_queue: VecDeque<ClientQueuedPrompt>,
    pub(crate) queue_selection: Option<usize>,
    pub(crate) queue_edit: Option<QueueEditState>,
    pub prompt_pending: bool,
    pub modes: Modes,
    pub skills: Vec<crate::bus::SkillInfo>,
    pub presets: Vec<crate::bus::CatalogPreset>,
    pub models: Vec<crate::bus::CatalogModel>,
    pub permission_choices: Vec<crate::bus::CatalogPreset>,
    pub effort_choices: Vec<String>,
    pub session_bound: bool,
    pub pending_steer_cells: HashMap<u64, PendingSteer>,
    pub subagents: Vec<SubagentView>,
    pub current_subagents: HashSet<String>,
    pub next_subagent_starts_batch: bool,
    pub active_subagent: Option<String>,
    pub agent_selection: Option<String>,
    /// A session-bound ACP ask (permission or elicitation) that arrived
    /// while this session was out of view — or that was on screen when the
    /// user switched away. Asks follow their session: only the live tab
    /// renders and answers them, switching never cancels one, and the tab
    /// strip marks a tab with a pending ask.
    pub permission_ask: Option<PermissionAskOverlay>,
    pub elicitation_ask: Option<ElicitationAskOverlay>,
    /// Painter-owned info popup (`/help`, `/keys`, `/session`, painter
    /// `/status` — `notify_plugin == false`) parked with its session: it
    /// leaves the screen on a switch and resurfaces, scroll and all, when
    /// the user returns. Compositor-owned plugin views never park — the
    /// tab-click path cancels them instead (see `cancel_plugin_overlays`).
    pub view_overlay: Option<ViewOverlay>,
    /// `/plugins` / `/cordis-plugins` inventory tree (selection state
    /// included) parked with its session like the info popups.
    pub plugin_tree: Option<PluginTree>,
}

impl SessionSlot {
    /// A fresh, empty session tab. `bound` is true only when the id is
    /// already a real session id (demo, local JSONL resume).
    pub(crate) fn fresh(id: String, bound: bool) -> Self {
        SessionSlot {
            transcript: Transcript::new(id.clone()),
            id,
            connection: None,
            title: None,
            input: ComposerEditor::new(),
            pending_images: crate::attachments::Staged::default(),
            input_expanded: false,
            file_menu: None,
            file_menu_dismissed: None,
            scroll_up: 0,
            selected_model: None,
            session_model: None,
            // A fresh tab has not prompted yet — the welcome banner paints
            // until its first send (resume paths force it off).
            show_banner: true,
            state_note: String::new(),
            run_started: None,
            running: false,
            completed_unseen: false,
            prompt_queue: VecDeque::new(),
            queue_selection: None,
            queue_edit: None,
            prompt_pending: false,
            modes: Modes::default(),
            skills: Vec::new(),
            presets: Vec::new(),
            models: Vec::new(),
            permission_choices: Vec::new(),
            effort_choices: Vec::new(),
            session_bound: bound,
            pending_steer_cells: HashMap::new(),
            subagents: Vec::new(),
            current_subagents: HashSet::new(),
            next_subagent_starts_batch: true,
            active_subagent: None,
            agent_selection: None,
            permission_ask: None,
            elicitation_ask: None,
            view_overlay: None,
            plugin_tree: None,
        }
    }
}

/// One FIFO entry for a tab awaiting its `SessionBound` (see the App
/// field `awaiting_binds`).
pub(crate) struct AwaitingBind {
    pub(crate) id: String,
    pub(crate) open: bool,
}

/// One row of the session tab strip (native chrome, `ui::draw_session_tabs`).
pub struct SessionTab {
    pub label: String,
    pub running: bool,
    pub completed_unseen: bool,
    /// A session-bound ACP ask (permission/elicitation) is pending on this
    /// tab — the agent is waiting for an answer only this tab can give.
    pub ask_pending: bool,
    pub current: bool,
}

pub(crate) const AGENT_HISTORY_ID: &str = "__crow_term_internal__:agent-history";

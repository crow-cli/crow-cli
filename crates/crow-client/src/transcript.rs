//! Transcript model: the scrollback cells and their rendering to styled lines.
//!
//! Mirrors what a harness session surfaces: user prompts, streaming
//! reasoning, streaming assistant text, tool calls with results, injected
//! context, subagent lifecycle, usage accounting, and turn outcomes.

use std::collections::HashMap;
use std::ops::Range;
use std::sync::Arc;
use std::time::Instant;

use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

use crate::events::{ToolDiff, UiEvent};
use crate::locale::Locale;
use crate::markdown::ToneMode;
use crate::theme::Theme;

/// Collapsed tool preview height; click toggles full expansion. Mouse wheel
/// always belongs to the outer transcript.
pub const TOOL_VIEWPORT: usize = 4;
/// Scrollback bound, mirroring crow_cli.tui's `prune_window` hysteresis
/// (`ui.prune_low_mark` 1500 + `ui.prune_excess` 1000 there). The transcript is
/// left completely alone until it exceeds `PRUNE_HIGH_ROWS`, then the oldest
/// settled cells are dropped until it is back under `PRUNE_LOW_ROWS`. The
/// 1000-row band is the amortization: one prune per 1000 new rows, not one per
/// frame. The marks sit far above crow-cli's because the windowed layout made
/// height free at paint time — this bounds memory, not frame cost.
pub const PRUNE_HIGH_ROWS: usize = 15_000;
pub const PRUNE_LOW_ROWS: usize = 14_000;
const COLLAPSED_SHELL_LINES: usize = 12;
const COLLAPSED_REASONING_PREVIEW: usize = 2;
/// Thumbnail width in cells (PNG images reserve a box of this many columns).
const THUMB_COLS: usize = 24;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NoticeLevel {
    Info,
    Warn,
    Error,
}

#[derive(Debug)]
pub enum CellKind {
    User {
        text: String,
        queued: bool,
    },
    Image {
        name: String,
        caption: String,
        /// Display path for the no-thumbnail fallback.
        path: String,
        /// Encoded raster bytes (PNG for the kitty thumbnail path).
        data: Arc<[u8]>,
        id: u32,
        queued: bool,
    },
    Reasoning {
        text: String,
        done: bool,
        started: Instant,
        seconds: Option<f32>,
        agent: Option<String>,
    },
    Assistant {
        text: String,
        done: bool,
        model: Option<String>,
        agent: Option<String>,
    },
    Tool {
        name: String,
        title: String,
        /// Raw ACP input, shown as a compact request block while pending.
        request: String,
        result: String,
        /// None while running.
        ok: Option<bool>,
        error: Option<String>,
        agent: Option<String>,
        /// A write/edit call's own artifact: the diff block off its content.
        /// When present it *is* the body — the card replaces both the raw
        /// input preview and the plain-text result tail.
        diff: Option<ToolDiff>,
    },
    Shell {
        command: String,
        /// None while running.
        output: Option<(Option<i32>, String)>,
    },
    Injected {
        source: String,
        preview: String,
    },
    /// Latest standard ACP plan snapshot. Replaced in place as statuses move.
    Plan {
        summary: String,
    },
    Notice {
        level: NoticeLevel,
        text: String,
    },
}

pub struct Cell {
    pub kind: CellKind,
    pub expanded: bool,
    pub hidden: bool,
    /// Content version, bumped by every mutation (streaming deltas, tool
    /// results, …) so the body render cache can detect staleness.
    version: u64,
    /// Cached body render for the wrap/markdown-heavy kinds. Headers stay
    /// outside the cache: they depend on the per-frame spinner and are cheap.
    render: Option<CellRender>,
    /// Cached row count under the layout inputs it was measured for. Written
    /// by the emitter itself (`layout_cells` records `out.len() - first`), so
    /// measuring a cell and painting it can never disagree. This is what lets
    /// the windowed path know a cell's height without materializing its lines.
    rows: Option<(LayoutKey, usize)>,
}

/// The layout inputs a cached row count or body render was built for. One key
/// type for both, so a cell can never hold a body measured for one width and a
/// row count for another.
#[derive(Clone, Copy, PartialEq)]
struct LayoutKey {
    version: u64,
    width: u16,
    theme: Theme,
    tone: ToneMode,
    /// The *effective* expansion, i.e. including the transcript-wide
    /// `collapse_all`; it decides Tool/Shell/Reasoning layout.
    expanded: bool,
    thumbs: bool,
    locale: Locale,
}

/// Cached body lines of one cell plus the layout inputs they were built for.
/// Body lines never depend on the spinner, so a spinning UI reuses them.
struct CellRender {
    key: LayoutKey,
    /// Lines below the cell header, in paint order, fully styled.
    body: Vec<Line<'static>>,
    /// Kind-specific count needed by the per-frame header: Tool cells carry
    /// the wrapped result line count (the `▸` chrome), Reasoning cells the
    /// wrapped body line count (`· N lines`). 0 when unused.
    meta: usize,
    /// Tool cells: the raw input yielded a command block, so an open cell
    /// leaves the one-line title out of the header rather than saying the
    /// same thing twice.
    has_command: bool,
}

/// Cached row prefix-sum over the cells: `sums[i]` is the number of laid-out
/// rows before cell `i`, so `sums[cells.len()]` is the transcript height and an
/// absolute line index maps back to its cell by binary search. `stamps[i]` is
/// the `(version, effective expanded)` that `sums[i + 1] - sums[i]` was
/// measured from — two integer compares per cell per frame, which is what keeps
/// the height of a 100k-row session cheap to know without laying any of it out.
struct Measure {
    width: u16,
    theme: Theme,
    tone: ToneMode,
    thumbs: bool,
    locale: Locale,
    collapse_all: bool,
    stamps: Vec<(u64, bool)>,
    sums: Vec<usize>,
}

/// What one `build_body` pass produced: the cacheable lines plus the two facts
/// the per-frame header needs about them.
struct BodyBuild {
    lines: Vec<Line<'static>>,
    meta: usize,
    has_command: bool,
}

impl BodyBuild {
    fn plain(lines: Vec<Line<'static>>, meta: usize) -> Self {
        BodyBuild {
            lines,
            meta,
            has_command: false,
        }
    }
}

impl Cell {
    fn new(kind: CellKind) -> Self {
        Cell {
            kind,
            // Thoughts and tool calls arrive open: the point of the transcript
            // is to read what the agent did, and a wall of `▸` chevrons makes
            // every turn a clicking exercise. ctrl+o collapses the lot, a
            // click collapses one.
            expanded: true,
            hidden: false,
            version: 0,
            render: None,
            rows: None,
        }
    }

    fn bump(&mut self) {
        self.version = self.version.wrapping_add(1);
    }

    /// The cache key for this cell under the given layout inputs. `expanded`
    /// is the *effective* value including the transcript-wide `collapse_all`.
    fn key(
        &self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        expanded: bool,
        thumbs: bool,
        locale: Locale,
    ) -> LayoutKey {
        LayoutKey {
            version: self.version,
            width,
            theme: *theme,
            tone,
            expanded,
            thumbs,
            locale,
        }
    }

    /// Return the cached body render, rebuilding it when the cell content
    /// version or any layout input (width/theme/tone/expanded/thumbs/locale)
    /// drifted.
    fn ensure_render(&mut self, key: LayoutKey) -> &CellRender {
        let stale = self.render.as_ref().is_none_or(|r| r.key != key);
        if stale {
            let built = build_body(
                &self.kind,
                &key.theme,
                key.tone,
                key.width as usize,
                key.expanded,
                key.thumbs,
                key.locale,
            );
            self.render = Some(CellRender {
                key,
                body: built.lines,
                meta: built.meta,
                has_command: built.has_command,
            });
        }
        self.render.as_ref().expect("body render built")
    }
}

/// Build the cacheable body lines for one cell: everything painted below the
/// per-frame header. Only the expensive kinds route through here;
/// User/Image/Injected/Plan/
/// Notice cells render fresh (their work is bounded and small).
fn build_body(
    kind: &CellKind,
    theme: &Theme,
    tone: ToneMode,
    width: usize,
    expanded: bool,
    _thumbs: bool,
    locale: Locale,
) -> BodyBuild {
    match kind {
        CellKind::Reasoning { text, .. } => {
            let body = text.trim();
            if body.is_empty() {
                return BodyBuild::plain(Vec::new(), 0);
            }
            // Thoughts render through the same markdown pipeline as
            // assistant text — structure, code frames, token colors — behind
            // a quote gutter that marks the block as thinking.
            let lines = crate::markdown::render_reasoning(body, theme, tone, width);
            let meta = lines.len();
            BodyBuild::plain(lines, meta)
        }
        CellKind::Assistant { text, .. } => {
            if text.trim().is_empty() {
                return BodyBuild::plain(Vec::new(), 0);
            }
            BodyBuild::plain(crate::markdown::render(text, theme, tone, width), 0)
        }
        CellKind::Tool {
            request,
            result,
            ok,
            error,
            diff,
            ..
        } => {
            // A write/edit call carries its own artifact, and the card *is*
            // the result: textual-diff-view's chrome (`📄 path (+N, -M)`,
            // dashed rule, `⋮` between hunks) painted full-bleed, since it
            // brings its own backgrounds and gutters. The raw-input preview
            // and the plain-text result tail would say the same thing twice,
            // so a card drops both; a failure still rides below it. Collapsed
            // is the card's own title row, which is the whole change in one
            // line -- the file and its counts.
            if let Some(d) = diff {
                let card = crate::diff::view::Diff::from_tool_diff(d);
                let full = card.lines(width);
                let total = full.len();
                let mut lines = if expanded {
                    full
                } else {
                    card.title_lines(width)
                };
                if let Some(err) = error {
                    lines.extend(error_rows(err, width, theme));
                }
                return BodyBuild {
                    lines,
                    meta: total,
                    has_command: false,
                };
            }
            let body = result.trim_end();
            let all: Vec<String> = if body.is_empty() {
                Vec::new()
            } else {
                body.lines()
                    .flat_map(|raw| wrap(raw, width.saturating_sub(2)))
                    .collect()
            };
            let total = all.len();
            let mut lines: Vec<Line> = Vec::new();
            let request = request.trim();
            let command = tool_command(request);
            if expanded {
                // Open: the command as a framed, language-labelled block,
                // through the same renderer assistant code fences use — and it
                // stays put after the call finishes, with the output below it.
                match &command {
                    Some((lang, code)) => {
                        let fence = format!("```{lang}\n{code}\n```");
                        for line in crate::markdown::render(
                            &fence,
                            theme,
                            tone,
                            width.saturating_sub(2),
                        ) {
                            let mut row = line;
                            row.spans.insert(
                                0,
                                Span::styled(
                                    "│ ".to_string(),
                                    Style::default().fg(theme.border),
                                ),
                            );
                            lines.push(row);
                        }
                    }
                    None if !request.is_empty() => lines.extend(tool_request_preview(
                        request, width, None, theme, locale,
                    )),
                    None => {}
                }
            } else if ok.is_none() && !request.is_empty() {
                // Closed and still running: the compact request preview, of
                // the command when there is one rather than of the wire's own
                // fencing around it.
                let preview = command
                    .as_ref()
                    .map_or(request, |(_, code)| code.as_str());
                lines.extend(tool_request_preview(
                    preview,
                    width,
                    Some(TOOL_VIEWPORT),
                    theme,
                    locale,
                ));
            }
            if let Some(err) = error {
                lines.extend(error_rows(err, width, theme));
            }
            if !body.is_empty() {
                let bar_color = match ok {
                    Some(false) => theme.err,
                    _ => theme.border,
                };
                if expanded || total <= TOOL_VIEWPORT {
                    for l in all {
                        lines.push(Line::from(vec![
                            Span::styled("│ ".to_string(), Style::default().fg(bar_color)),
                            Span::styled(l, Style::default().fg(theme.fg_tertiary)),
                        ]));
                    }
                } else {
                    let offset = total - TOOL_VIEWPORT;
                    for l in all.into_iter().skip(offset) {
                        lines.push(Line::from(vec![
                            Span::styled("│ ".to_string(), Style::default().fg(bar_color)),
                            Span::styled(l, Style::default().fg(theme.fg_tertiary)),
                        ]));
                    }
                    lines.push(Line::from(vec![
                        Span::styled("│ ".to_string(), Style::default().fg(bar_color)),
                        Span::styled(
                            locale.trf(
                                "last {}/{} lines · click to expand",
                                "末尾 {}/{} 行 · 点击展开",
                                &[TOOL_VIEWPORT.to_string(), total.to_string()],
                            ),
                            Style::default().fg(theme.caption),
                        ),
                    ]));
                }
            }
            BodyBuild {
                lines,
                meta: total,
                has_command: command.is_some(),
            }
        }
        CellKind::Shell { output, .. } => {
            let mut lines: Vec<Line> = Vec::new();
            if let Some((code, text)) = output {
                let body_w = width.saturating_sub(2);
                let card_row = |txt: &str, fg: ratatui::style::Color| -> Line<'static> {
                    let pad = body_w.saturating_sub(unicode_width::UnicodeWidthStr::width(txt));
                    Line::from(vec![
                        Span::styled(
                            "▎ ".to_string(),
                            Style::default().fg(theme.hint).bg(theme.code_bg),
                        ),
                        Span::styled(
                            format!("{txt}{}", " ".repeat(pad)),
                            Style::default().fg(fg).bg(theme.code_bg),
                        ),
                    ])
                };
                let all: Vec<String> = text
                    .trim_end()
                    .lines()
                    .flat_map(|raw| wrap(raw, body_w))
                    .collect();
                let total = all.len();
                // Collapsed view keeps the *tail* — errors and results live
                // at the end of shell output, and the Tool cell collapses
                // the same direction (last N lines).
                let shown = if expanded || total <= COLLAPSED_SHELL_LINES {
                    all
                } else {
                    all.into_iter().skip(total - COLLAPSED_SHELL_LINES).collect()
                };
                let shown_len = shown.len();
                for l in shown {
                    lines.push(card_row(&l, theme.fg_secondary));
                }
                if total > shown_len {
                    lines.push(card_row(
                        &locale.trf(
                            "… +{} lines (ctrl+o expands)",
                            "… +{} 行（ctrl+o 展开）",
                            &[(total - shown_len).to_string()],
                        ),
                        theme.caption,
                    ));
                }
                if let Some(c) = code {
                    if *c != 0 {
                        lines.push(card_row(
                            &locale.trf("exit {}", "退出码 {}", &[c.to_string()]),
                            theme.err,
                        ));
                    }
                }
            }
            BodyBuild::plain(lines, 0)
        }
        _ => BodyBuild::plain(Vec::new(), 0),
    }
}

/// A tool failure's message, wrapped behind the red gutter the rest of the
/// cell's body uses.
fn error_rows(err: &str, width: usize, theme: &Theme) -> Vec<Line<'static>> {
    wrap(err, width.saturating_sub(2))
        .into_iter()
        .map(|l| {
            Line::from(vec![
                Span::styled("│ ".to_string(), Style::default().fg(theme.err)),
                Span::styled(l, Style::default().fg(theme.err)),
            ])
        })
        .collect()
}

/// One image the UI should render as a kitty-graphics thumbnail, positioned
/// by its reserved line range (`line` is relative to the transcript layout;
/// the chat pane adds its banner offset).
pub struct ImageShot {
    pub id: u32,
    pub line: usize,
    pub rows: usize,
    pub cols: usize,
    pub data: Arc<[u8]>,
}

/// One user prompt in a rendered transcript: the transcript cell index and
/// the half-open line span `[line, end)` its bubble occupies (the leading
/// blank separator row is not counted; `end` covers wrapped text lines and,
/// for image prompts, the thumbnail rows). The ↥ composer button walks
/// these from the newest one back and flashes the jumped span (issue #103).
#[derive(Clone, Copy, Debug)]
pub struct UserPromptLine {
    pub cell: usize,
    pub line: usize,
    pub end: usize,
}

/// A rendered transcript: styled lines plus, for each line, the index of the
/// transcript cell that owns it (only tool cells report ownership, so mouse
/// clicks can toggle a specific tool preview).
pub struct TranscriptLayout {
    pub lines: Vec<Line<'static>>,
    pub owners: Vec<Option<usize>>,
    pub images: Vec<ImageShot>,
    /// Every laid-out user prompt with the index of its first text line.
    pub users: Vec<UserPromptLine>,
}

#[derive(Default, Clone, Copy)]
pub struct UsageTotals {
    pub input: u64,
    pub output: u64,
    pub cached: u64,
    pub reasoning: u64,
}

/// The latest ACP `usage_update` reading: tokens currently in context against
/// the agent's compaction ceiling. Absolute, so each update overwrites the last.
#[derive(Default, Clone, Copy, PartialEq, Eq, Debug)]
pub struct ContextUsage {
    pub used: u64,
    pub size: u64,
}

impl ContextUsage {
    /// Fraction of the context window consumed, `0.0..=1.0`. A zero `size`
    /// (agent sent no ceiling) reads as empty rather than dividing by zero.
    pub fn fraction(&self) -> f64 {
        if self.size == 0 {
            return 0.0;
        }
        (self.used as f64 / self.size as f64).clamp(0.0, 1.0)
    }
}

/// Native transcript timing/step facts used by session state and tests. The
/// LLM usage/timing details surface through `/session` (and the Client-side
/// `acpSessionStats` service for plugins), not a persistent status row.
#[derive(Default, Clone, Copy)]
pub struct SessionStats {
    pub turns: u64,
    pub steps: u64,
    /// Total turn wall time (turn/start → turn/end).
    pub turn_millis: u64,
    /// Time spent inside tool calls (tool/call → tool/result).
    pub tool_millis: u64,
    /// Sum of per-turn time-to-first-token, plus how many turns were sampled.
    pub ttft_total_millis: u64,
    pub ttft_count: u64,
}

pub struct Transcript {
    pub cells: Vec<Cell>,
    root_session: String,
    open_assistant: HashMap<String, usize>,
    open_reasoning: HashMap<String, usize>,
    tools: HashMap<String, usize>,
    agents: HashMap<String, String>,
    agent_seq: usize,
    image_seq: u32,
    plan_cell: Option<usize>,
    pub usage: UsageTotals,
    /// Latest context-window meter from `usage_update`; `None` until the
    /// agent sends one.
    pub context: Option<ContextUsage>,
    pub stats: SessionStats,
    turn_started: Option<Instant>,
    tool_started: HashMap<String, Instant>,
    ttft_pending: bool,
    pub last_finish: Option<String>,
    /// Provenance-reported model of the last assembled assistant message —
    /// the ground truth of what actually answered.
    pub last_model: Option<String>,
    /// Transcript-wide override from ctrl+o. Cells arrive open, so the
    /// override's job is the other direction: while it is set every
    /// Tool/Shell/Reasoning body falls back to its preview regardless of the
    /// per-cell toggle, and clearing it hands control back to the cells.
    pub collapse_all: bool,
    /// UI language for the notices this transcript renders (set by the App
    /// that owns it; cells already pushed keep the language they had).
    pub locale: Locale,
    /// Bumped by `clear()`. Long-lived cell-index handles (shell results,
    /// steer echoes) carry the generation they were pushed in, so stale
    /// indexes can never land in a freshly cleared transcript.
    gen: u64,
    /// Row prefix-sum cache; see `Measure`. Dropped whenever the layout inputs
    /// drift or the cell count changes.
    measure: Option<Measure>,
}

impl Transcript {
    pub fn new(root_session: String) -> Self {
        Transcript {
            cells: Vec::new(),
            root_session,
            open_assistant: HashMap::new(),
            open_reasoning: HashMap::new(),
            tools: HashMap::new(),
            agents: HashMap::new(),
            agent_seq: 0,
            image_seq: 0,
            plan_cell: None,
            usage: UsageTotals::default(),
            context: None,
            stats: SessionStats::default(),
            turn_started: None,
            tool_started: HashMap::new(),
            ttft_pending: false,
            last_finish: None,
            last_model: None,
            collapse_all: false,
            locale: Locale::default(),
            gen: 0,
            measure: None,
        }
    }

    /// Transcript generation: changes whenever `clear()` empties the cells,
    /// invalidating cell-index handles held elsewhere.
    pub fn gen(&self) -> u64 {
        self.gen
    }

    pub fn set_root_session(&mut self, session: String) {
        self.root_session = session;
        self.open_assistant.clear();
        self.open_reasoning.clear();
        self.tools.clear();
        self.agents.clear();
        self.plan_cell = None;
        self.usage = UsageTotals::default();
        self.context = None;
        self.stats = SessionStats::default();
        self.turn_started = None;
        self.tool_started.clear();
        self.ttft_pending = false;
    }

    pub fn clear(&mut self) {
        self.cells.clear();
        self.open_assistant.clear();
        self.open_reasoning.clear();
        self.tools.clear();
        self.plan_cell = None;
        self.last_finish = None;
        self.gen = self.gen.wrapping_add(1);
    }

    /// Drop the oldest cells until the laid-out height is back under
    /// [`PRUNE_LOW_ROWS`]. `rows` is the height `measure` just reported, so this
    /// costs no layout of its own. Returns the number of rows removed, or 0
    /// when nothing was pruned.
    ///
    /// Pruning shifts every cell index and bumps [`Self::gen`], so it refuses
    /// to run while any cell is still in flight — an open stream, a tool
    /// awaiting its result, a shell awaiting its output. Callers that hold cell
    /// indexes of their own (steer echoes, pending local shells) must gate on
    /// those too; see `App::prune_scrollback`.
    pub fn prune_oldest(&mut self, rows: usize) -> usize {
        if rows <= PRUNE_HIGH_ROWS {
            return 0;
        }
        // Smallest cut that lands at or under the low mark: `sums` is
        // non-decreasing, so the first prefix whose removal is enough.
        let (cut, removed) = {
            let Some(sums) = self.measure.as_ref().map(|m| &m.sums) else {
                return 0;
            };
            let cut = sums
                .partition_point(|&s| rows.saturating_sub(s) > PRUNE_LOW_ROWS)
                .min(self.settled_prefix());
            (cut, sums.get(cut).copied().unwrap_or(0))
        };
        if cut == 0 {
            return 0;
        }
        self.cells.drain(0..cut);
        for map in [
            &mut self.open_assistant,
            &mut self.open_reasoning,
            &mut self.tools,
        ] {
            map.retain(|_, idx| *idx >= cut);
            for idx in map.values_mut() {
                *idx -= cut;
            }
        }
        self.plan_cell = self.plan_cell.and_then(|c| c.checked_sub(cut));
        // The prefix-sum no longer lines up with the cells, and every index
        // this transcript ever handed out just moved.
        self.measure = None;
        self.gen = self.gen.wrapping_add(1);
        removed
    }

    /// Count of leading cells that have finished. Pruning never cuts into an
    /// unsettled cell, so this is the hard ceiling on a cut.
    fn settled_prefix(&self) -> usize {
        self.cells
            .iter()
            .position(|cell| match &cell.kind {
                CellKind::Assistant { done, .. } => !*done,
                CellKind::Reasoning { done, .. } => !*done,
                CellKind::Tool { ok, .. } => ok.is_none(),
                CellKind::Shell { output, .. } => output.is_none(),
                _ => false,
            })
            .unwrap_or(self.cells.len())
    }

    fn agent_label(&self, session: &str) -> Option<String> {
        if session == self.root_session || session.is_empty() {
            None
        } else {
            self.agents
                .get(session)
                .cloned()
                .or_else(|| Some("agent".into()))
        }
    }

    pub fn push_user(&mut self, text: String, queued: bool) {
        self.cells.push(Cell::new(CellKind::User { text, queued }));
    }

    /// Record a user-sent image (bytes kept for the kitty thumbnail path).
    pub fn push_image(
        &mut self,
        name: String,
        caption: String,
        path: String,
        data: Arc<[u8]>,
        queued: bool,
    ) {
        self.image_seq += 1;
        let id = self.image_seq;
        self.cells.push(Cell::new(CellKind::Image {
            name,
            caption,
            path,
            data,
            id,
            queued,
        }));
    }

    pub fn push_notice(&mut self, level: NoticeLevel, text: String) {
        self.cells.push(Cell::new(CellKind::Notice { level, text }));
    }

    pub fn push_shell(&mut self, command: String) -> usize {
        self.cells.push(Cell::new(CellKind::Shell {
            command,
            output: None,
        }));
        self.cells.len() - 1
    }

    pub fn finish_shell(&mut self, idx: usize, code: Option<i32>, output: String, gen: u64) {
        if gen != self.gen {
            return; // the cell died with a /clear or resume replay
        }
        if let Some(cell) = self.cells.get_mut(idx) {
            if let CellKind::Shell { output: slot, .. } = &mut cell.kind {
                *slot = Some((code, output));
            }
            cell.bump();
        }
    }

    pub fn hide_cells(&mut self, cells: &[usize], gen: u64) {
        if gen != self.gen {
            return; // stale handles from before a clear
        }
        for &index in cells {
            if let Some(cell) = self.cells.get_mut(index) {
                cell.hidden = true;
                // Hiding changes the row count, so the measure cache has to
                // see it as a content change.
                cell.bump();
            }
        }
    }

    /// Backchat `session.tool_cancelled` on user stop: in-flight tools and
    /// streams stop spinning before `session/prompt` unwinds.
    pub fn cancel_open_work(&mut self) {
        self.settle_open_tools("cancelled");
        for cell in &mut self.cells {
            let mutated = match &mut cell.kind {
                CellKind::Reasoning {
                    done,
                    started,
                    seconds,
                    ..
                } if !*done => {
                    *done = true;
                    *seconds = Some(started.elapsed().as_secs_f32());
                    true
                }
                CellKind::Assistant { done, .. } if !*done => {
                    *done = true;
                    true
                }
                CellKind::Shell { output, .. } if output.is_none() => {
                    *output = Some((None, self.locale.tr("cancelled", "已取消").to_string()));
                    true
                }
                _ => false,
            };
            if mutated {
                cell.bump();
            }
        }
        self.open_assistant.clear();
        self.open_reasoning.clear();
        self.last_finish = Some("cancelled".into());
    }

    /// Settle client presentation for calls whose owning prompt turn stopped
    /// without a terminal ACP tool update. This is deliberately not a wire
    /// `failed` event: the adapter's last reported status remains unchanged.
    fn settle_open_tools(&mut self, reason: &str) {
        let text = match reason {
            "cancelled" => self.locale.tr("cancelled", "已取消").to_string(),
            "interrupted" => self.locale.tr("interrupted", "已中断").to_string(),
            "turn ended" => self.locale.tr("turn ended", "本轮结束").to_string(),
            other => other.to_string(),
        };
        for idx in self.tools.values().copied().collect::<Vec<_>>() {
            if let Some(cell) = self.cells.get_mut(idx) {
                if let CellKind::Tool {
                    ok, result, error, ..
                } = &mut cell.kind
                {
                    if ok.is_none() {
                        *ok = Some(false);
                        *error = Some(text.clone());
                        if result.is_empty() {
                            *result = text.clone();
                        }
                    }
                }
                cell.bump();
            }
        }
        self.tools.clear();
        self.tool_started.clear();
    }

    fn close_open(&mut self, session: &str) {
        if let Some(idx) = self.open_assistant.remove(session) {
            if let Some(cell) = self.cells.get_mut(idx) {
                if let CellKind::Assistant { done, text, .. } = &mut cell.kind {
                    *done = true;
                    if text.trim().is_empty() {
                        // Leave the empty husk; render skips empty finished cells.
                    }
                }
                cell.bump();
            }
        }
        if let Some(idx) = self.open_reasoning.remove(session) {
            if let Some(cell) = self.cells.get_mut(idx) {
                if let CellKind::Reasoning {
                    done,
                    started,
                    seconds,
                    ..
                } = &mut cell.kind
                {
                    *done = true;
                    *seconds = Some(started.elapsed().as_secs_f32());
                }
                cell.bump();
            }
        }
    }

    fn close_all_open(&mut self) {
        let sessions: Vec<String> = self
            .open_assistant
            .keys()
            .chain(self.open_reasoning.keys())
            .cloned()
            .collect();
        for s in sessions {
            self.close_open(&s);
        }
    }

    /// Record the per-turn first-token latency when the first visible or
    /// reasoning delta for the root session arrives.
    fn note_first_token(&mut self, session: &str) {
        if session != self.root_session || !self.ttft_pending {
            return;
        }
        if let Some(t0) = self.turn_started {
            self.stats.ttft_total_millis += t0.elapsed().as_millis() as u64;
            self.stats.ttft_count += 1;
        }
        self.ttft_pending = false;
    }

    pub fn apply(&mut self, ev: UiEvent) {
        match ev {
            UiEvent::SessionStatus { session, running } => {
                if !running && session == self.root_session {
                    self.close_all_open();
                }
            }
            UiEvent::TurnStart { session, .. } => {
                if session == self.root_session {
                    self.stats.turns += 1;
                    self.turn_started = Some(Instant::now());
                    self.ttft_pending = true;
                }
            }
            UiEvent::TurnEnd { session, kind } => {
                self.close_open(&session);
                if session == self.root_session {
                    self.settle_open_tools(if kind == "interrupted" {
                        "interrupted"
                    } else {
                        "turn ended"
                    });
                    self.last_finish = Some(kind.clone());
                    if let Some(t0) = self.turn_started.take() {
                        self.stats.turn_millis += t0.elapsed().as_millis() as u64;
                    }
                    if kind != "completed" && kind != "interrupted" {
                        let level = if kind == "error" {
                            NoticeLevel::Error
                        } else {
                            NoticeLevel::Warn
                        };
                        self.push_notice(
                            level,
                            self.locale
                                .trf("turn ended: {}", "本轮结束：{}", &[kind.clone()]),
                        );
                    }
                }
            }
            UiEvent::TextDelta { session, text } => {
                self.note_first_token(&session);
                // Reasoning for this step is over once visible text streams.
                if let Some(idx) = self.open_reasoning.remove(&session) {
                    if let Some(cell) = self.cells.get_mut(idx) {
                        if let CellKind::Reasoning {
                            done,
                            started,
                            seconds,
                            ..
                        } = &mut cell.kind
                        {
                            *done = true;
                            *seconds = Some(started.elapsed().as_secs_f32());
                        }
                        cell.bump();
                    }
                }
                let idx = match self.open_assistant.get(&session) {
                    Some(&idx) => idx,
                    None => {
                        let agent = self.agent_label(&session);
                        self.cells.push(Cell::new(CellKind::Assistant {
                            text: String::new(),
                            done: false,
                            model: None,
                            agent,
                        }));
                        let idx = self.cells.len() - 1;
                        self.open_assistant.insert(session.clone(), idx);
                        idx
                    }
                };
                if let Some(cell) = self.cells.get_mut(idx) {
                    if let CellKind::Assistant { text: buf, .. } = &mut cell.kind {
                        buf.push_str(&text);
                    }
                    cell.bump();
                }
            }
            UiEvent::ReasoningDelta { session, text } => {
                self.note_first_token(&session);
                let idx = match self.open_reasoning.get(&session) {
                    Some(&idx) => idx,
                    None => {
                        let agent = self.agent_label(&session);
                        self.cells.push(Cell::new(CellKind::Reasoning {
                            text: String::new(),
                            done: false,
                            started: Instant::now(),
                            seconds: None,
                            agent,
                        }));
                        let idx = self.cells.len() - 1;
                        self.open_reasoning.insert(session.clone(), idx);
                        idx
                    }
                };
                if let Some(cell) = self.cells.get_mut(idx) {
                    if let CellKind::Reasoning { text: buf, .. } = &mut cell.kind {
                        buf.push_str(&text);
                    }
                    cell.bump();
                }
            }
            UiEvent::ToolCallPreparing { session } => {
                self.close_open(&session);
            }
            UiEvent::AssistantFinal {
                session,
                text,
                model,
            } => {
                if session == self.root_session {
                    self.stats.steps += 1;
                }
                if model.is_some() && session == self.root_session {
                    self.last_model = model.clone();
                }
                let idx = self.open_assistant.remove(&session);
                match idx {
                    Some(idx) => {
                        if let Some(cell) = self.cells.get_mut(idx) {
                            if let CellKind::Assistant {
                                text: buf,
                                done,
                                model: m,
                                ..
                            } = &mut cell.kind
                            {
                                if !text.is_empty() {
                                    *buf = text;
                                }
                                *done = true;
                                *m = model;
                            }
                            cell.bump();
                        }
                    }
                    None => {
                        if !text.is_empty() {
                            let agent = self.agent_label(&session);
                            self.cells.push(Cell::new(CellKind::Assistant {
                                text,
                                done: true,
                                model,
                                agent,
                            }));
                        }
                    }
                }
            }
            UiEvent::ToolCall {
                session,
                call_id,
                name,
                arguments,
                diff,
            } => {
                self.close_open(&session);
                let title = tool_title(&name, &arguments);
                if let Some(&idx) = self.tools.get(&call_id) {
                    if let Some(cell) = self.cells.get_mut(idx) {
                        if let CellKind::Tool {
                            name: current_name,
                            title: current_title,
                            request,
                            diff: current_diff,
                            ..
                        } = &mut cell.kind
                        {
                            *current_name = name;
                            *current_title = title;
                            *request = arguments;
                            // An upsert patches: the update carrying the
                            // artifact fills the card in, and one that does
                            // not carry it leaves the card already there alone.
                            if diff.is_some() {
                                *current_diff = diff;
                            }
                        }
                        cell.bump();
                    }
                    return;
                }
                if session == self.root_session {
                    self.tool_started.insert(call_id.clone(), Instant::now());
                }
                let agent = self.agent_label(&session);
                self.cells.push(Cell::new(CellKind::Tool {
                    name,
                    title,
                    request: arguments,
                    result: String::new(),
                    ok: None,
                    error: None,
                    agent,
                    diff,
                }));
                self.tools.insert(call_id, self.cells.len() - 1);
            }
            UiEvent::ToolResult {
                session,
                call_id,
                is_error,
                text,
                error,
            } => {
                if session == self.root_session {
                    if let Some(t0) = self.tool_started.remove(&call_id) {
                        self.stats.tool_millis += t0.elapsed().as_millis() as u64;
                    }
                }
                let idx = self.tools.remove(&call_id);
                match idx {
                    Some(idx) => {
                        if let Some(cell) = self.cells.get_mut(idx) {
                            if let CellKind::Tool {
                                request,
                                result,
                                ok,
                                error: e,
                                ..
                            } = &mut cell.kind
                            {
                                *result = without_command_echo(request, &text);
                                *ok = Some(!is_error);
                                *e = error;
                            }
                            cell.bump();
                        }
                    }
                    None => {
                        let agent = self.agent_label(&session);
                        self.cells.push(Cell::new(CellKind::Tool {
                            name: "tool".into(),
                            title: call_id,
                            request: String::new(),
                            result: text,
                            ok: Some(!is_error),
                            error,
                            agent,
                            diff: None,
                        }));
                    }
                }
            }
            UiEvent::Usage {
                input,
                output,
                cached,
                reasoning,
                ..
            } => {
                self.usage.input += input;
                self.usage.output += output;
                self.usage.cached += cached;
                self.usage.reasoning += reasoning;
            }
            // Absolute reading: overwrite, never accumulate.
            UiEvent::ContextUsage { used, size, .. } => {
                self.context = Some(ContextUsage { used, size });
            }
            UiEvent::UserInjected {
                source, preview, ..
            } => {
                self.cells
                    .push(Cell::new(CellKind::Injected { source, preview }));
            }
            UiEvent::UserMessage { text, .. } => {
                self.push_user(text, false);
            }
            UiEvent::SessionTitle { title, .. } => {
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale
                        .trf("session · {}", "会话 · {}", &[title.clone()]),
                );
            }
            UiEvent::SessionNotice {
                severity,
                title,
                details,
                ..
            } => {
                let level = match severity.as_str() {
                    "warning" | "warn" => NoticeLevel::Warn,
                    "error" => NoticeLevel::Error,
                    _ => NoticeLevel::Info,
                };
                let text = details
                    .filter(|details| details != &title)
                    .map(|details| format!("{title} — {details}"))
                    .unwrap_or(title);
                self.push_notice(level, text);
            }
            UiEvent::SessionModel { .. } => {}
            UiEvent::Plan { summary, .. } => {
                if let Some(idx) = self.plan_cell {
                    if let Some(cell) = self.cells.get_mut(idx) {
                        if let CellKind::Plan { summary: current } = &mut cell.kind {
                            *current = summary.clone();
                        }
                        cell.bump();
                    } else {
                        self.plan_cell = None;
                    }
                }
                if self.plan_cell.is_none() {
                    self.cells.push(Cell::new(CellKind::Plan { summary }));
                    self.plan_cell = Some(self.cells.len() - 1);
                }
            }
            UiEvent::SubagentStarted { child, .. } => {
                self.agent_seq += 1;
                let label = self
                    .locale
                    .trf("subagent {}", "子代理 {}", &[self.agent_seq.to_string()]);
                self.agents.insert(child, label);
            }
            UiEvent::SubagentFinished { .. } => {}
            UiEvent::PlanMode { active, .. } => {
                let state = if active {
                    self.locale.tr("on", "开")
                } else {
                    self.locale.tr("off", "关")
                };
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale
                        .trf("⌁ plan mode {}", "⌁ 计划模式 {}", &[state.to_string()]),
                );
            }
            UiEvent::SandboxMode { mode, .. } => {
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale
                        .trf("⛨ file policy · {}", "⛨ 文件策略 · {}", &[mode.clone()]),
                );
            }
            UiEvent::ApprovalPolicy { policy, .. } => {
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale.trf(
                        "⚖ approval policy · {}",
                        "⚖ 审批策略 · {}",
                        &[policy.clone()],
                    ),
                );
            }
            UiEvent::PermissionPreset { preset, .. } => {
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale.trf(
                        "⛨ permission · {}",
                        "⛨ 权限 · {}",
                        &[preset.clone()],
                    ),
                );
            }
            UiEvent::AgentPreset { preset, .. } => {
                self.push_notice(
                    NoticeLevel::Info,
                    self.locale.trf(
                        "⚙ agent preset · {}",
                        "⚙ Agent 预设 · {}",
                        &[preset.clone()],
                    ),
                );
            }
            UiEvent::ReasoningEffort { .. } => {}
            UiEvent::ApprovalAsked { tool, reason, .. } => {
                let why = reason.map(|r| format!(" · {r}")).unwrap_or_default();
                self.push_notice(
                    NoticeLevel::Warn,
                    self.locale.trf(
                        "⚖ approval requested · {}{}",
                        "⚖ 请求审批 · {}{}",
                        &[tool.clone(), why],
                    ),
                );
            }
            UiEvent::ApprovalDecided { outcome, .. } => {
                let level = if outcome.contains("reject") || outcome.contains("denied") {
                    NoticeLevel::Warn
                } else {
                    NoticeLevel::Info
                };
                self.push_notice(
                    level,
                    self.locale
                        .trf("⚖ approval · {}", "⚖ 审批 · {}", &[outcome.clone()]),
                );
            }
            UiEvent::Palette { .. } => {}
        }
    }

    /// Is any assistant/reasoning cell currently streaming?
    pub fn streaming(&self) -> bool {
        !self.open_assistant.is_empty() || !self.open_reasoning.is_empty()
    }

    /// Reasoning already renders its own live `thinking…` row. Assistant
    /// streaming does not: its next visible event may be a complete tool call.
    pub fn reasoning_streaming(&self) -> bool {
        !self.open_reasoning.is_empty()
    }

    /// Render every cell to wrapped, styled lines for `width` columns.
    #[allow(dead_code)] // kept for tests; the UI uses `layout` for ownership
    pub fn lines(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
    ) -> Vec<Line<'static>> {
        self.layout(theme, tone, width, spinner, false).lines
    }

    /// Render every cell to wrapped, styled lines, plus per-line ownership so
    /// the UI can route mouse clicks to a specific tool preview (and only tool
    /// lines claim ownership). `thumbs` reserves blank
    /// lines for kitty-graphics image thumbnails and reports their placements.
    pub fn layout(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
        thumbs: bool,
    ) -> TranscriptLayout {
        let end = self.cells.len();
        self.layout_cells(theme, tone, width, spinner, thumbs, 0..end, 0)
    }

    /// Total laid-out row count, refreshing the cached prefix-sum on the way.
    /// A cell whose content version and effective expansion are unchanged costs
    /// two integer compares; only drifted cells get laid out, and only to count
    /// their rows. This is the cheap half of the viewport split — `draw_chat`
    /// needs the height to resolve its scroll window before it can know which
    /// cells are worth painting.
    fn measure(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
        thumbs: bool,
    ) -> usize {
        let width = width.max(8);
        let n = self.cells.len();
        let collapse_all = self.collapse_all;
        let locale = self.locale;
        // Take the table out so the rebuild loop can borrow `self` mutably.
        let mut table = self.measure.take();
        let reusable = table.as_ref().is_some_and(|m| {
            m.width == width
                && m.theme == *theme
                && m.tone == tone
                && m.thumbs == thumbs
                && m.locale == locale
                && m.collapse_all == collapse_all
                && m.stamps.len() == n
        });
        let mut t = if reusable {
            table.take().expect("reusable table")
        } else {
            Measure {
                width,
                theme: *theme,
                tone,
                thumbs,
                locale,
                collapse_all,
                // A stamp no cell can match, so every entry reads as dirty.
                stamps: vec![(u64::MAX, false); n],
                sums: vec![0; n + 1],
            }
        };
        t.stamps.resize(n, (u64::MAX, false));
        t.sums.resize(n + 1, 0);
        // Sums before the first drifted cell are still valid, so the rebuild
        // starts there — a streaming tail re-measures one cell, not the lot.
        let dirty = (0..n)
            .find(|&ci| {
                t.stamps[ci] != (self.cells[ci].version, self.cells[ci].expanded && !collapse_all)
            })
            .unwrap_or(n);
        for ci in dirty..n {
            let expanded = self.cells[ci].expanded && !collapse_all;
            let stamp = (self.cells[ci].version, expanded);
            let cached = self.cells[ci].rows.as_ref().and_then(|(k, rows)| {
                (k.version == stamp.0
                    && k.width == width
                    && k.theme == *theme
                    && k.tone == tone
                    && k.expanded == expanded
                    && k.thumbs == thumbs
                    && k.locale == locale)
                    .then_some(*rows)
            });
            let rows = match cached {
                Some(rows) => rows,
                // Cold at this width/theme/expansion: lay the one cell out to
                // count it. `layout_cells` records the count as it emits, so
                // the next frame reads it instead of rebuilding.
                None => self
                    .layout_cells(theme, tone, width, spinner, thumbs, ci..ci + 1, 0)
                    .lines
                    .len(),
            };
            t.sums[ci + 1] = t.sums[ci] + rows;
            t.stamps[ci] = stamp;
        }
        let total = t.sums[n];
        self.measure = Some(t);
        total
    }

    /// Total laid-out row count without materializing any of them. The chat
    /// pane needs this to resolve its scroll window before it can know which
    /// cells are worth painting; see `measure`.
    pub fn row_count(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
        thumbs: bool,
    ) -> usize {
        self.measure(theme, tone, width, spinner, thumbs)
    }

    /// Lay out only the cells intersecting the absolute line window
    /// `start..end`. Returns the layout, the transcript's total row count, and
    /// `base` — the absolute line the returned `lines[0]` sits at, so the caller
    /// slices `lines[start - base..end - base]` for the screen. Reported
    /// `users`/`images` line numbers stay absolute, exactly as in `layout`.
    pub fn layout_window(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
        thumbs: bool,
        start: usize,
        end: usize,
    ) -> (TranscriptLayout, usize, usize) {
        let total = self.measure(theme, tone, width, spinner, thumbs);
        let n = self.cells.len();
        // `sums` is non-decreasing, so both ends of the cell range come from a
        // binary search rather than a walk.
        let (first, last, base) = {
            let sums = &self.measure.as_ref().expect("measured").sums;
            // First cell owning a row at or after `start`: the cell before the
            // first prefix that exceeds it.
            let lo = sums.partition_point(|&s| s <= start);
            let first = lo.saturating_sub(1).min(n);
            // First cell starting at or after `end` — the exclusive upper bound.
            let last = sums.partition_point(|&s| s < end).clamp(first, n);
            let base = if first < n { sums[first] } else { total };
            (first, last, base)
        };
        let layout = self.layout_cells(theme, tone, width, spinner, thumbs, first..last, base);
        (layout, total, base)
    }

    /// Lay out only `range`'s cells, numbering every reported line index from
    /// `base_line`. This is the whole viewport story: the chat pane needs the
    /// *height* of the transcript to resolve its scroll window, but only the
    /// *lines* of the cells that intersect it. `measure` supplies the heights
    /// from the per-cell row cache this function fills in as it emits, so a
    /// frame paints ~one screenful of cells no matter how long the session is.
    ///
    /// `owners` values are cell indexes (already absolute); `users`/`images`
    /// line numbers are absolute transcript lines, so a windowed layout and a
    /// full one report the same coordinates.
    fn layout_cells(
        &mut self,
        theme: &Theme,
        tone: ToneMode,
        width: u16,
        spinner: char,
        thumbs: bool,
        range: Range<usize>,
        base_line: usize,
    ) -> TranscriptLayout {
        let width = width.max(8) as usize;
        let collapse_all = self.collapse_all;
        let locale = self.locale;
        let mut out: Vec<Line> = Vec::new();
        let mut owners: Vec<Option<usize>> = Vec::new();
        let mut images: Vec<ImageShot> = Vec::new();
        let mut users: Vec<UserPromptLine> = Vec::new();
        for ci in range {
            let cell = &mut self.cells[ci];
            let expanded = cell.expanded && !collapse_all;
            let key = cell.key(theme, tone, width as u16, expanded, thumbs, locale);
            let cell_first = out.len();
            if cell.hidden {
                cell.rows = Some((key, 0));
                continue;
            }
            // Wrap/markdown-heavy kinds paint their body lines from the
            // per-cell render cache (see `Cell::ensure_render`); headers stay
            // live so the spinner keeps turning without re-wrapping bodies.
            if matches!(
                &cell.kind,
                CellKind::Reasoning { .. }
                    | CellKind::Assistant { .. }
                    | CellKind::Tool { .. }
                    | CellKind::Shell { .. }
            ) {
                cell.ensure_render(key);
            }
            // A cell that emits nothing (empty assistant text, empty plan)
            // still has to record its zero height, so it breaks out of the
            // block rather than continuing the loop.
            'cell: {
            match &cell.kind {
                CellKind::User { text, queued } => {
                    emit(&mut out, &mut owners, Line::default(), None);
                    // Web UI fidelity: the user bubble paints with its own
                    // token pair (`bubble_bg` / `bubble_fg`), not the assistant
                    // surface.
                    // Budget = width - 4: the "❯ "/"  " prefix takes 2 cells
                    // and the " {l} " padding takes 2 more, so a wider wrap
                    // budget would clip the last text cells of full lines.
                    let first = out.len();
                    for (i, l) in wrap(text, width.saturating_sub(4)).into_iter().enumerate() {
                        let mut spans = vec![
                            Span::styled(
                                if i == 0 { "❯ " } else { "  " }.to_string(),
                                Style::default()
                                    .fg(theme.brand)
                                    .add_modifier(Modifier::BOLD),
                            ),
                            Span::styled(
                                format!(" {l} "),
                                Style::default()
                                    .fg(theme.bubble_fg)
                                    .bg(theme.bubble_bg)
                                    .add_modifier(Modifier::BOLD),
                            ),
                        ];
                        if i == 0 && *queued {
                            spans.push(Span::styled(
                                "  queued".to_string(),
                                Style::default().fg(theme.warn_soft()),
                            ));
                        }
                        emit(&mut out, &mut owners, Line::from(spans), None);
                    }
                    users.push(UserPromptLine {
                        cell: ci,
                        line: base_line + first,
                        end: base_line + out.len(),
                    });
                }
                CellKind::Image {
                    name,
                    caption,
                    path,
                    data,
                    id,
                    queued,
                    ..
                } => {
                    emit(&mut out, &mut owners, Line::default(), None);
                    let first = out.len();
                    let label = if caption.is_empty() {
                        format!("🖼 {name}")
                    } else {
                        format!("🖼 {name} · {caption}")
                    };
                    let mut spans = vec![
                        Span::styled(
                            "❯ ".to_string(),
                            Style::default()
                                .fg(theme.brand)
                                .add_modifier(Modifier::BOLD),
                        ),
                        Span::styled(
                            format!(" {label} "),
                            Style::default()
                                .fg(theme.bubble_fg)
                                .bg(theme.bubble_bg)
                                .add_modifier(Modifier::BOLD),
                        ),
                    ];
                    if *queued {
                        spans.push(Span::styled(
                            "  queued".to_string(),
                            Style::default().fg(theme.warn_soft()),
                        ));
                    }
                    emit(&mut out, &mut owners, Line::from(spans), None);

                    // Thumbnail (PNG only — clipboard screenshots are PNG;
                    // other formats fall back to the path line below).
                    let is_png = data.starts_with(b"\x89PNG\r\n\x1a\n");
                    if thumbs && is_png {
                        if let Some((w, h)) = crate::pet::image_dims(data) {
                            let cols = (width.saturating_sub(2)).min(THUMB_COLS);
                            let rows = thumb_rows(cols, w, h) as usize;
                            let line = out.len();
                            for _ in 0..rows {
                                emit(&mut out, &mut owners, Line::default(), None);
                            }
                            images.push(ImageShot {
                                id: *id,
                                line: base_line + line,
                                rows,
                                cols,
                                data: data.clone(),
                            });
                        } else {
                            emit(
                                &mut out,
                                &mut owners,
                                Line::from(Span::styled(
                                    format!("  {path}"),
                                    Style::default().fg(theme.caption),
                                )),
                                None,
                            );
                        }
                    } else {
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(Span::styled(
                                format!("  {path}"),
                                Style::default().fg(theme.caption),
                            )),
                            None,
                        );
                    }
                    users.push(UserPromptLine {
                        cell: ci,
                        line: base_line + first,
                        end: base_line + out.len(),
                    });
                }
                CellKind::Reasoning {
                    done,
                    started,
                    seconds,
                    agent,
                    ..
                } => {
                    let render = cell.render.as_ref().expect("body cache");
                    emit(&mut out, &mut owners, Line::default(), None);
                    let head_style = Style::default().fg(theme.caption);
                    // A reasoning stream can open with an empty/whitespace
                    // delta. The heading is enough for that frame; an empty
                    // body must not make its height jump from one row to two.
                    let n = render.meta;
                    if *done {
                        let dur = seconds.map(|s| format!(" · {s:.1}s")).unwrap_or_default();
                        let agent = agent_prefix(agent);
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(Span::styled(
                                format!("✻ {agent}thought{dur} · {n} line{}", plural(n)),
                                head_style,
                            )),
                            None,
                        );
                        if expanded {
                            for l in &render.body {
                                emit(&mut out, &mut owners, l.clone(), None);
                            }
                        }
                    } else {
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(Span::styled(
                                format!(
                                    "✻ {}thinking… {}s",
                                    agent_prefix(agent),
                                    started.elapsed().as_secs()
                                ),
                                Style::default().fg(theme.brand_soft),
                            )),
                            None,
                        );
                        let skip = if expanded {
                            0
                        } else {
                            render.body.len().saturating_sub(COLLAPSED_REASONING_PREVIEW)
                        };
                        for l in &render.body[skip..] {
                            emit(&mut out, &mut owners, l.clone(), None);
                        }
                    }
                }
                CellKind::Assistant {
                    text, done, agent, ..
                } => {
                    if text.trim().is_empty() {
                        break 'cell;
                    }
                    emit(&mut out, &mut owners, Line::default(), None);
                    if let Some(a) = agent {
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(Span::styled(
                                format!("⛭ {a}"),
                                Style::default().fg(theme.caption),
                            )),
                            None,
                        );
                    }
                    let render = cell.render.as_ref().expect("body cache");
                    for l in &render.body {
                        emit(&mut out, &mut owners, l.clone(), None);
                    }
                    if !done && !render.body.is_empty() {
                        // streaming cursor
                        if let Some(last) = out.last_mut() {
                            last.spans.push(Span::styled(
                                "▍".to_string(),
                                Style::default().fg(theme.brand),
                            ));
                        }
                    }
                }
                CellKind::Tool {
                    name,
                    title,
                    ok,
                    agent,
                    diff,
                    ..
                } => {
                    let render = cell.render.as_ref().expect("body cache");
                    emit(&mut out, &mut owners, Line::default(), None);
                    let total = render.meta;
                    let has_more = total > TOOL_VIEWPORT;
                    let (glyph, gstyle) = match ok {
                        None => (spinner, Style::default().fg(theme.brand)),
                        Some(true) => ('⏺', Style::default().fg(theme.ok_soft())),
                        Some(false) => ('⏺', Style::default().fg(theme.err)),
                    };
                    let mut spans = vec![
                        Span::styled(format!("{glyph} "), gstyle),
                        Span::styled(
                            name.clone(),
                            Style::default().fg(theme.fg).add_modifier(Modifier::BOLD),
                        ),
                    ];
                    if let Some(a) = agent {
                        spans.push(Span::styled(
                            format!(" · {a}"),
                            Style::default().fg(theme.caption),
                        ));
                    }
                    // An open cell frames the command below the header, so the
                    // one-line title would only say the same thing twice. A
                    // diff card repeats it in both states: its own title row
                    // carries the path and the counts, and the wire title for
                    // such a call is that same path again.
                    let titled = !title.is_empty()
                        && !(expanded && render.has_command)
                        && diff.is_none();
                    if titled {
                        let prefix_w: usize = spans.iter().map(|s| s.content.width()).sum();
                        let chevron_w = if has_more { 2 } else { 0 };
                        let budget = width.saturating_sub(prefix_w + 2 + chevron_w);
                        spans.push(Span::styled(
                            format!("  {}", clamp_str(title, budget)),
                            Style::default().fg(theme.fg_tertiary),
                        ));
                    }
                    if has_more {
                        spans.push(Span::styled(
                            if expanded { " ▾" } else { " ▸" }.to_string(),
                            Style::default().fg(theme.caption),
                        ));
                    }
                    emit(&mut out, &mut owners, Line::from(spans), Some(ci));

                    for l in &render.body {
                        emit(&mut out, &mut owners, l.clone(), Some(ci));
                    }
                }
                CellKind::Shell { command, output } => {
                    emit(&mut out, &mut owners, Line::default(), None);
                    let (glyph, gstyle) = match output {
                        None => (spinner, Style::default().fg(theme.warn_soft())),
                        Some((Some(0), _)) => ('!', Style::default().fg(theme.ok_soft())),
                        Some(_) => ('!', Style::default().fg(theme.err)),
                    };
                    // Terminal card: `$ cmd` chip in the header, output as
                    // full-width code_bg rows behind a gray-blue gutter.
                    emit(
                        &mut out,
                        &mut owners,
                        Line::from(vec![
                            Span::styled(format!("{glyph} "), gstyle.add_modifier(Modifier::BOLD)),
                            Span::styled(
                                format!(" $ {command} "),
                                Style::default()
                                    .fg(theme.bubble_fg)
                                    .bg(theme.bubble_bg)
                                    .add_modifier(Modifier::BOLD),
                            ),
                            Span::styled(
                                "  local shell".to_string(),
                                Style::default().fg(theme.caption),
                            ),
                        ]),
                        None,
                    );
                    let render = cell.render.as_ref().expect("body cache");
                    for l in &render.body {
                        emit(&mut out, &mut owners, l.clone(), None);
                    }
                }
                CellKind::Injected { source, preview } => {
                    emit(
                        &mut out,
                        &mut owners,
                        Line::from(vec![
                            Span::styled(
                                "◦ context".to_string(),
                                Style::default().fg(theme.caption),
                            ),
                            Span::styled(
                                format!(" · {source} · "),
                                Style::default().fg(theme.caption),
                            ),
                            Span::styled(
                                clamp_str(
                                    preview,
                                    width.saturating_sub(
                                        UnicodeWidthStr::width(source.as_str()) + 15,
                                    ),
                                ),
                                Style::default().fg(theme.fg_tertiary),
                            ),
                        ]),
                        None,
                    );
                }
                CellKind::Plan { summary } => {
                    if summary.is_empty() {
                        break 'cell;
                    }
                    for l in wrap(
                        &locale.trf("plan · {}", "计划 · {}", &[summary.clone()]),
                        width.saturating_sub(2),
                    ) {
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(vec![
                                Span::styled("· ".to_string(), Style::default().fg(theme.caption)),
                                Span::styled(l, Style::default().fg(theme.caption)),
                            ]),
                            None,
                        );
                    }
                }
                CellKind::Notice { level, text } => {
                    let color = match level {
                        NoticeLevel::Info => theme.caption,
                        NoticeLevel::Warn => theme.warn_soft(),
                        NoticeLevel::Error => theme.err,
                    };
                    for l in wrap(text, width.saturating_sub(2)) {
                        emit(
                            &mut out,
                            &mut owners,
                            Line::from(vec![
                                Span::styled("· ".to_string(), Style::default().fg(color)),
                                Span::styled(l, Style::default().fg(color)),
                            ]),
                            None,
                        );
                    }
                }
            }
            }
            cell.rows = Some((key, out.len() - cell_first));
        }
        TranscriptLayout {
            lines: out,
            owners,
            images,
            users,
        }
    }
}

fn emit(
    out: &mut Vec<Line<'static>>,
    owners: &mut Vec<Option<usize>>,
    line: Line<'static>,
    owner: Option<usize>,
) {
    out.push(line);
    owners.push(owner);
}

/// Thumbnail height in rows for `cols` columns, preserving the image's pixel
/// aspect under the same 2:1 cell aspect the composer pet assumes.
fn thumb_rows(cols: usize, w: u32, h: u32) -> usize {
    if w == 0 || h == 0 || cols == 0 {
        return 6;
    }
    let rows = (cols as f64 * h as f64 / (2.0 * w as f64)).round() as usize;
    rows.clamp(2, 12)
}

fn plural(n: usize) -> &'static str {
    if n == 1 {
        ""
    } else {
        "s"
    }
}

fn agent_prefix(agent: &Option<String>) -> String {
    match agent {
        Some(a) => format!("{a} "),
        None => String::new(),
    }
}

/// Human title for a tool call, parsed from its raw JSON argument string.
pub fn tool_title(name: &str, arguments: &str) -> String {
    // A command that arrived already fenced titles the cell with its code —
    // the markers around it are the wire's, not something to read.
    if let Some((_, code, _)) = split_leading_fence(arguments) {
        if !code.trim().is_empty() {
            return one_line(code.trim());
        }
    }
    let parsed: Option<serde_json::Value> = serde_json::from_str(arguments).ok();
    if let Some(v) = parsed {
        match name {
            "bash" => {
                if let Some(cmd) = v.get("command").and_then(|c| c.as_str()) {
                    return one_line(cmd);
                }
            }
            "str_replace_editor" => {
                let cmd = v.get("command").and_then(|c| c.as_str()).unwrap_or("");
                let path = v.get("path").and_then(|c| c.as_str()).unwrap_or("");
                if !cmd.is_empty() || !path.is_empty() {
                    return one_line(&format!("{cmd} {path}"));
                }
            }
            _ => {}
        }
        // generic: compact json
        return one_line(&v.to_string());
    }
    one_line(arguments)
}

fn one_line(s: &str) -> String {
    clamp_str(&s.replace('\n', " ⏎ "), 120)
}

/// The `request  `-labelled preview of a tool's raw input, capped to `take`
/// lines when the cell is closed.
fn tool_request_preview(
    request: &str,
    width: usize,
    take: Option<usize>,
    theme: &Theme,
    locale: Locale,
) -> Vec<Line<'static>> {
    let label = locale.tr("request  ", "请求  ").to_string();
    let pad = " ".repeat(label.width());
    let request_width = width.saturating_sub(2 + label.width());
    let wrapped = wrap(request, request_width.max(1));
    let rows: Vec<String> = match take {
        Some(n) => wrapped.into_iter().take(n).collect(),
        None => wrapped,
    };
    rows.into_iter()
        .enumerate()
        .map(|(index, line)| {
            Line::from(vec![
                Span::styled("│ ".to_string(), Style::default().fg(theme.border)),
                Span::styled(
                    if index == 0 { label.clone() } else { pad.clone() },
                    Style::default().fg(theme.caption),
                ),
                Span::styled(line, Style::default().fg(theme.fg_tertiary)),
            ])
        })
        .collect()
}

/// The command inside a tool call's raw input, and the language to frame it as.
///
/// ACP hands over `rawInput` JSON and agents put the interesting part in a
/// well-known field, so a kernel cell reads as python and a shell call as bash
/// instead of both collapsing into one gray JSON blob. `None` when the input
/// carries nothing worth framing.
pub(crate) fn tool_command(request: &str) -> Option<(&'static str, String)> {
    // An agent that fences the command itself needs no unpacking, only a
    // language worth tokenizing.
    if let Some((lang, code, _)) = split_leading_fence(request) {
        if !code.trim().is_empty() {
            return Some((lang_token(lang), code.to_owned()));
        }
    }
    let value: serde_json::Value = serde_json::from_str(request).ok()?;
    let object = value.as_object()?;
    let field = |keys: &[&str]| -> Option<String> {
        keys.iter().find_map(|key| {
            object
                .get(*key)
                .and_then(serde_json::Value::as_str)
                .map(str::trim)
                .filter(|text| !text.is_empty())
                .map(str::to_owned)
        })
    };
    if let Some(code) = field(&["code"]) {
        return Some(("python", code));
    }
    match object.get("command") {
        Some(serde_json::Value::String(command)) if !command.trim().is_empty() => {
            return Some(("bash", command.trim().to_owned()));
        }
        Some(serde_json::Value::Array(argv)) => {
            let joined = argv
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
                .join(" ");
            if !joined.trim().is_empty() {
                return Some(("bash", joined));
            }
        }
        _ => {}
    }
    // A file-writing tool: the payload is the command and the path names the
    // language.
    if let (Some(path), Some(payload)) = (
        field(&["path", "file_path", "filename"]),
        field(&["file_text", "new_str", "new_string", "content"]),
    ) {
        return Some((lang_for_path(&path), payload));
    }
    if object.is_empty() {
        return None;
    }
    // Anything else: the raw input itself, spread out enough to read.
    Some(("json", serde_json::to_string_pretty(&value).ok()?))
}

/// A request that arrived as a fenced block: `(language, code, rest)`.
///
/// crow-cli puts the kernel cell in the tool call's `content` already fenced
/// for markdown, and repeats it ahead of the output on completion. crow
/// draws its own frame, so the markers are unpacked rather than rendered.
fn split_leading_fence(text: &str) -> Option<(&str, &str, &str)> {
    let (head, tail) = text.split_once('\n')?;
    let lang = head.trim().strip_prefix("```")?.trim();
    let close = tail.find("\n```")?;
    let code = &tail[..close];
    let rest = &tail[close + 1..];
    let rest = rest.strip_prefix("```").unwrap_or(rest);
    Some((lang, code, rest.split_once('\n').map_or("", |(_, r)| r)))
}

/// Drop a completion's echo of the command the cell already frames.
///
/// ACP clients merge an update's fields over the call's start, so an agent
/// that rides `content` has to repeat it to keep it; without this the code
/// would be drawn twice, once framed and once as output.
fn without_command_echo(request: &str, text: &str) -> String {
    let Some((_, code)) = tool_command(request) else {
        return text.to_owned();
    };
    match split_leading_fence(text) {
        Some((_, echoed, rest)) if echoed.trim() == code.trim() => {
            rest.trim_start_matches('\n').to_owned()
        }
        _ => text.to_owned(),
    }
}

/// Fence label for a file path's extension — what syntect then tokenizes.
fn lang_for_path(path: &str) -> &'static str {
    let ext = std::path::Path::new(path)
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default();
    lang_token(ext)
}

/// Every label [`lang_token`] can return. `highlight`'s tests hold this to
/// syntect's default set: each one either resolves to a grammar or is one of
/// the two named-but-uncolored labels below.
#[cfg(test)]
pub(crate) const LANG_TOKENS: &[&str] = &[
    "python",
    "rust",
    "javascript",
    "typescript",
    "bash",
    "json",
    "markdown",
    "toml",
    "yaml",
    "html",
    "css",
    "sql",
    "c",
    "cpp",
    "go",
    "ruby",
    "lua",
    "java",
    "php",
    "diff",
    "xml",
    "makefile",
    "latex",
    "haskell",
    "scala",
    "perl",
    "r",
    "text",
];

/// The language a fence label or file extension names, normalized to the token
/// a frame is labelled with. Labels the default grammars do not cover (TOML,
/// plain text) still name the language; they just render uncolored.
fn lang_token(label: &str) -> &'static str {
    match label.trim().to_ascii_lowercase().as_str() {
        "py" | "pyi" | "python" | "python3" => "python",
        "rs" | "rust" => "rust",
        "js" | "mjs" | "cjs" | "jsx" | "javascript" | "node" => "javascript",
        "ts" | "tsx" | "typescript" => "typescript",
        "sh" | "bash" | "zsh" | "shell" | "console" => "bash",
        "json" | "jsonc" => "json",
        "md" | "markdown" => "markdown",
        "toml" => "toml",
        "yaml" | "yml" => "yaml",
        "html" | "htm" => "html",
        "css" => "css",
        "sql" => "sql",
        "c" | "h" => "c",
        "cc" | "cpp" | "cxx" | "hpp" | "c++" => "cpp",
        "go" => "go",
        "rb" | "ruby" => "ruby",
        "lua" => "lua",
        "java" => "java",
        "php" => "php",
        "diff" | "patch" => "diff",
        "xml" | "xsl" | "xsd" => "xml",
        "make" | "mk" | "makefile" => "makefile",
        "tex" | "latex" => "latex",
        "hs" | "haskell" => "haskell",
        "scala" => "scala",
        "pl" | "pm" | "perl" => "perl",
        "r" => "r",
        _ => "text",
    }
}

/// Grapheme clusters of `s` with their terminal display width.
///
/// Cells are painted per grapheme (ratatui measures with
/// `UnicodeSegmentation` + `UnicodeWidthStr`), so wrapping and truncation must
/// use the same unit. A ZWJ family emoji is one 2-cell cluster even though its
/// chars sum to 6 cells, and `❤️` is 2 cells though its chars sum to 1 — the
/// per-`char` sums this module used before split clusters and mismeasured
/// lines.
pub(crate) fn graphemes_with_width(s: &str) -> impl DoubleEndedIterator<Item = (&str, usize)> {
    UnicodeSegmentation::graphemes(s, true).map(|g| (g, UnicodeWidthStr::width(g)))
}

pub(crate) fn clamp_str(s: &str, max: usize) -> String {
    if max == 0 {
        return String::new();
    }
    let s = expand_tabs(s);
    if s.width() <= max {
        return s;
    }
    let mut out = String::new();
    let mut w = 0usize;
    let budget = max.saturating_sub(1);
    for (g, cw) in graphemes_with_width(&s) {
        if w + cw > budget {
            break;
        }
        out.push_str(g);
        w += cw;
    }
    out.push('…');
    out
}

/// Expand tabs to spaces at 8-column stops so wrap/layout width matches
/// what a terminal actually paints (a raw `\t` is otherwise width 0/1).
fn expand_tabs(s: &str) -> String {
    let mut out = String::new();
    let mut col = 0usize;
    for (g, cw) in graphemes_with_width(s) {
        if g == "\t" {
            let pad = 8 - (col % 8);
            out.push_str(&" ".repeat(pad));
            col += pad;
        } else {
            out.push_str(g);
            col += cw;
        }
    }
    out
}

/// Greedy display-width wrap with word-boundary preference; never panics on
/// CJK/emoji. Tabs expand to spaces before wrapping so a tab-indented source
/// line cannot paint past `width` (issue #5).
pub fn wrap(text: &str, width: usize) -> Vec<String> {
    let width = width.max(4);
    let mut out = Vec::new();
    for raw in text.split('\n') {
        if raw.is_empty() {
            out.push(String::new());
            continue;
        }
        let raw = expand_tabs(raw);
        let mut line = String::new();
        let mut w = 0usize;
        for (g, cw) in graphemes_with_width(&raw) {
            if w + cw > width && !line.is_empty() {
                // Prefer breaking at the last space when it is not too early.
                match line.rfind(' ') {
                    Some(bidx) if line[..bidx].width() >= width / 2 => {
                        let tail = line[bidx + 1..].to_string();
                        line.truncate(bidx);
                        out.push(std::mem::replace(&mut line, tail));
                        w = line.width();
                    }
                    _ => {
                        out.push(std::mem::take(&mut line));
                        w = 0;
                    }
                }
            }
            if w + cw > width && !line.is_empty() {
                out.push(std::mem::take(&mut line));
                w = 0;
            }
            line.push_str(g);
            w += cw;
        }
        out.push(line);
    }
    if out.is_empty() {
        out.push(String::new());
    }
    out
}

#[cfg(test)]
#[path = "../tests/unit/transcript__tests.rs"]
mod tests;

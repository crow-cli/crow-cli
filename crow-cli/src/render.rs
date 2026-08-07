//! Pretty CLI renderer for ACP v2 session updates.
//!
//! NOT a TUI — just really good println! with ANSI colors.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use agent_client_protocol::schema::v2 as acp;
use agent_client_protocol::schema::MaybeUndefined;

const RESET: &str = "\x1b[0m";
const DIM: &str = "\x1b[2m";
const RED: &str = "\x1b[31m";
const GREEN: &str = "\x1b[32m";
const YELLOW: &str = "\x1b[33m";
const BLUE: &str = "\x1b[34m";
const MAGENTA: &str = "\x1b[35m";
const CYAN: &str = "\x1b[36m";
const BOLD: &str = "\x1b[1m";
const BOLD_RED: &str = "\x1b[1;31m";
const BOLD_GREEN: &str = "\x1b[1;32m";

fn tool_icon(kind: Option<&acp::ToolKind>) -> &'static str {
    match kind {
        Some(acp::ToolKind::Read) => "📖",
        Some(acp::ToolKind::Edit) => "✏️",
        Some(acp::ToolKind::Delete) => "🗑️",
        Some(acp::ToolKind::Move) => "📦",
        Some(acp::ToolKind::Search) => "🔍",
        Some(acp::ToolKind::Execute) => "⚡",
        Some(acp::ToolKind::Think) => "🧠",
        Some(acp::ToolKind::Fetch) => "🌐",
        Some(acp::ToolKind::SwitchMode) => "🔀",
        _ => "🔧",
    }
}

/// Box color per tool kind (12.1).
fn tool_color(kind: Option<&acp::ToolKind>) -> &'static str {
    match kind {
        Some(acp::ToolKind::Read) => CYAN,
        Some(acp::ToolKind::Edit) => YELLOW,
        Some(acp::ToolKind::Delete) | Some(acp::ToolKind::Move) => MAGENTA,
        Some(acp::ToolKind::Search) | Some(acp::ToolKind::Fetch) => BLUE,
        Some(acp::ToolKind::Execute) => GREEN,
        _ => DIM,
    }
}

/// Helper to extract &T from MaybeUndefined<T>.
fn mu_ref<T>(mu: &MaybeUndefined<T>) -> Option<&T> {
    match mu {
        MaybeUndefined::Value(v) => Some(v),
        _ => None,
    }
}

/// Terminal width via TIOCGWINSZ; 80 when unknown (pipes, CI).
fn terminal_width() -> usize {
    unsafe {
        let mut ws: libc::winsize = std::mem::zeroed();
        if libc::ioctl(libc::STDOUT_FILENO, libc::TIOCGWINSZ, &mut ws) == 0 && ws.ws_col > 0 {
            ws.ws_col as usize
        } else {
            80
        }
    }
}

/// Shared drain buffer for the markdown renderer: `Renderer<W>` owns its
/// writer, so we hand it a clone of this handle and drain from our side.
#[derive(Clone, Default)]
struct MdBuf(Arc<Mutex<Vec<u8>>>);

impl Write for MdBuf {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(buf);
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl MdBuf {
    fn drain(&self) -> Vec<u8> {
        std::mem::take(&mut *self.0.lock().unwrap())
    }
}

struct ToolState {
    #[allow(dead_code)]
    title: String,
    kind: Option<acp::ToolKind>,
}

/// Stored state of an agent-owned terminal (patch semantics per ACP).
#[derive(Default)]
struct TermState {
    command: Option<String>,
    /// Raw terminal bytes (ANSI intact), decoded from base64 snapshots/chunks.
    raw: Vec<u8>,
    exit_code: Option<u32>,
    /// True when output was live-streamed via TerminalOutputChunk — the
    /// Completed branch must not re-render the snapshot (double-print).
    streamed: bool,
    /// True when the command header box was already printed at Pending —
    /// the Completed branch must not print it again.
    header_printed: bool,
}

pub struct CliRenderer {
    tools: HashMap<String, ToolState>,
    terminals: HashMap<String, TermState>,
    has_message: bool,
    /// Last emitted stream was thinking — separate it from what follows.
    last_was_thought: bool,
    // ---- streaming markdown (agent text) ----
    md_parser: streamdown_parser::Parser,
    md_renderer: streamdown_render::Renderer<MdBuf>,
    md_buf: MdBuf,
    /// Partial line not yet handed to the parser (chunks split mid-line).
    md_line: String,
    /// message_id of the markdown document currently being streamed.
    md_msg_id: Option<String>,
}

impl CliRenderer {
    pub fn new() -> Self {
        let md_buf = MdBuf::default();
        let mut md_renderer =
            streamdown_render::Renderer::new(md_buf.clone(), terminal_width());
        // No surprise clipboard writes / temp files from rendered code blocks.
        md_renderer.set_clipboard(false);
        md_renderer.set_savebrace(false);
        Self {
            tools: HashMap::new(),
            terminals: HashMap::new(),
            has_message: false,
            last_was_thought: false,
            md_parser: streamdown_parser::Parser::new(),
            md_renderer,
            md_buf,
            md_line: String::new(),
            md_msg_id: None,
        }
    }

    /// Feed streamed agent text into the markdown pipeline. One document per
    /// ACP message_id; a change flushes the previous doc.
    fn md_feed(&mut self, out: &mut impl Write, message_id: &str, text: &str) {
        if self.md_msg_id.as_deref() != Some(message_id) {
            self.md_finish(out);
            self.md_msg_id = Some(message_id.to_string());
        }
        for ch in text.chars() {
            if ch == '\n' {
                let line = std::mem::take(&mut self.md_line);
                for event in self.md_parser.parse_line(&line) {
                    let _ = self.md_renderer.render_event(&event);
                }
            } else {
                self.md_line.push(ch);
            }
        }
        let bytes = self.md_buf.drain();
        if !bytes.is_empty() {
            let _ = out.write_all(&bytes);
            let _ = out.flush();
            self.has_message = true;
            self.last_was_thought = false;
        }
    }

    /// Render a complete message (resume replay) through the markdown
    /// pipeline as one document.
    fn md_full_message(
        &mut self,
        out: &mut impl Write,
        message_id: &str,
        content: Option<&Vec<acp::ContentBlock>>,
    ) {
        let Some(blocks) = content else { return };
        for block in blocks {
            if let acp::ContentBlock::Text(t) = block {
                self.md_feed(out, message_id, &t.text);
            }
        }
        self.md_finish(out);
    }

    /// Close the current markdown document: flush the partial line, finalize
    /// open blocks (unclosed fences etc.), drain, reset for the next doc.
    /// Parser+renderer are reused across documents (spike-verified: output is
    /// byte-identical to a fresh instance).
    fn md_finish(&mut self, out: &mut impl Write) {
        if self.md_msg_id.is_none() && self.md_line.is_empty() {
            return;
        }
        if !self.md_line.is_empty() {
            let line = std::mem::take(&mut self.md_line);
            for event in self.md_parser.parse_line(&line) {
                let _ = self.md_renderer.render_event(&event);
            }
        }
        for event in self.md_parser.finalize() {
            let _ = self.md_renderer.render_event(&event);
        }
        self.md_parser.reset();
        let bytes = self.md_buf.drain();
        if !bytes.is_empty() {
            let _ = out.write_all(&bytes);
            let _ = out.flush();
        }
        self.md_msg_id = None;
    }

    pub fn handle_update(&mut self, update: &acp::SessionUpdate) {
        let stdout = std::io::stdout();
        let mut out = stdout.lock();
        self.handle_update_to(&mut out, update);
    }

    /// Same as `handle_update`, but writes to `out` (testability, 12.1).
    pub fn handle_update_to(&mut self, mut out: &mut impl Write, update: &acp::SessionUpdate) {

        // Anything that isn't a continuation of the streamed markdown doc
        // (new message, tool call, terminal bytes, idle) closes the doc first.
        let continues = match update {
            acp::SessionUpdate::AgentMessageChunk(c) => {
                self.md_msg_id.as_deref() == Some(c.message_id.0.as_ref())
            }
            acp::SessionUpdate::AgentThoughtChunk(c) => {
                self.md_msg_id.as_deref() == Some(c.message_id.0.as_ref())
            }
            _ => false,
        };
        if !continues {
            self.md_finish(&mut out);
        }

        match update {
            acp::SessionUpdate::AgentMessageChunk(chunk) => {
                if let acp::ContentBlock::Text(text) = &chunk.content {
                    let new_doc =
                        self.md_msg_id.as_deref() != Some(chunk.message_id.0.as_ref());
                    // Thinking just ended and the agent starts actually
                    // responding — a markdown --- divider between the two.
                    if new_doc && self.last_was_thought {
                        self.md_feed(&mut out, chunk.message_id.0.as_ref(), "---\n");
                    }
                    self.md_feed(&mut out, chunk.message_id.0.as_ref(), &text.text);
                }
            }

            acp::SessionUpdate::AgentThoughtChunk(chunk) => {
                if let acp::ContentBlock::Text(text) = &chunk.content {
                    let new_doc =
                        self.md_msg_id.as_deref() != Some(chunk.message_id.0.as_ref());
                    // Start of a thinking phase (first thought after
                    // non-thought output): a brain above the thinking content.
                    if new_doc && !self.last_was_thought {
                        let _ = writeln!(out, "🧠");
                    }
                    self.md_feed(&mut out, chunk.message_id.0.as_ref(), &text.text);
                    self.last_was_thought = true;
                }
            }

            // Whole-message updates (resume replay) — same pipeline.
            acp::SessionUpdate::AgentMessage(msg) => {
                self.md_full_message(&mut out, msg.message_id.0.as_ref(), mu_ref(&msg.content));
            }
            acp::SessionUpdate::UserMessage(msg) => {
                self.md_full_message(&mut out, msg.message_id.0.as_ref(), mu_ref(&msg.content));
            }

            acp::SessionUpdate::ToolCallUpdate(tc) => {
                self.render_tool_call(&mut out, tc);
            }

            acp::SessionUpdate::TerminalUpdate(tu) => {
                let st = self
                    .terminals
                    .entry(tu.terminal_id.to_string())
                    .or_default();
                if let Some(cmd) = mu_ref(&tu.command) {
                    st.command = Some(cmd.clone());
                }
                match &tu.output {
                    MaybeUndefined::Value(o) => {
                        st.raw = decode_b64(&o.data);
                    }
                    MaybeUndefined::Null => st.raw.clear(),
                    _ => {}
                }
                if let Some(exit) = mu_ref(&tu.exit_status) {
                    st.exit_code = exit.exit_code;
                }
            }

            acp::SessionUpdate::TerminalOutputChunk(chunk) => {
                let bytes = decode_b64(&chunk.data);
                let st = self
                    .terminals
                    .entry(chunk.terminal_id.to_string())
                    .or_default();
                st.raw.extend_from_slice(&bytes);
                st.streamed = true;
                // Live pass-through: raw PTY bytes (ANSI intact) straight to
                // the user's terminal — full color, no emulation.
                let _ = out.write_all(&bytes);
                let _ = out.flush();
            }

            acp::SessionUpdate::StateUpdate(su) => {
                if let acp::StateUpdate::Idle(_) = su {
                    if self.has_message || self.last_was_thought {
                        let _ = writeln!(out);
                    }
                    self.has_message = false;
                    self.last_was_thought = false;
                }
            }

            _ => {}
        }
    }

    fn render_tool_call(&mut self, out: &mut impl Write, tc: &acp::ToolCallUpdate) {
        let id = tc.tool_call_id.to_string();
        let status = mu_ref(&tc.status);

        match status {
            Some(acp::ToolCallStatus::Pending) => {
                let title = mu_ref(&tc.title)
                    .map(|s| s.as_str())
                    .unwrap_or("tool")
                    .to_string();
                let kind = mu_ref(&tc.kind).cloned();
                let icon = tool_icon(kind.as_ref());
                let color = tool_color(kind.as_ref());

                if self.has_message || self.last_was_thought {
                    let _ = writeln!(out);
                    self.has_message = false;
                    self.last_was_thought = false;
                }

                // Box top (12.1): one box per tool call, colored by kind.
                let _ = writeln!(out, "{color}┌─ {icon} {title} ──────{RESET}");

                // Terminal tool: the client already knows the command from
                // raw_input — print it in full immediately, never truncate.
                if let Some(command) = mu_ref(&tc.raw_input)
                    .and_then(|v| v.get("command"))
                    .and_then(|v| v.as_str())
                {
                    let mut lines = command.lines();
                    if let Some(first) = lines.next() {
                        let _ = writeln!(out, "{color}│{RESET} {DIM}$ {first}{RESET}");
                        for line in lines {
                            let _ = writeln!(out, "{color}│{RESET} {DIM}  {line}{RESET}");
                        }
                    }
                    let st = self.terminals.entry(format!("term_{id}")).or_default();
                    st.command = Some(command.to_string());
                    st.header_printed = true;
                }

                self.tools.insert(id, ToolState { title, kind });
            }

            Some(acp::ToolCallStatus::Completed) => {
                let state = self.tools.get(&id);
                let kind = state
                    .and_then(|s| s.kind.clone())
                    .or_else(|| mu_ref(&tc.kind).cloned());
                let color = tool_color(kind.as_ref());
                if state.is_none() {
                    // Never saw Pending (defensive, e.g. replay gap): open late.
                    let icon = tool_icon(kind.as_ref());
                    let title = mu_ref(&tc.title).map(|s| s.as_str()).unwrap_or("tool");
                    let _ = writeln!(out, "{color}┌─ {icon} {title} ──────{RESET}");
                }

                let mut is_terminal = false;
                let mut exit_code: Option<u32> = None;
                if let Some(content) = mu_ref(&tc.content) {
                    for item in content {
                        match item {
                            acp::ToolCallContent::Diff(diff) => {
                                let _ = writeln!(out);
                                render_diff(out, diff, &format!("{color}│{RESET}"));
                            }
                            acp::ToolCallContent::Content(boxed) => {
                                if let acp::ContentBlock::Text(text) = &boxed.content {
                                    let _ = writeln!(
                                        out,
                                        "{color}│{RESET} {DIM}{}{RESET}",
                                        truncate(&text.text, 200)
                                    );
                                }
                            }
                            acp::ToolCallContent::Terminal(t) => {
                                is_terminal = true;
                                let st = self.terminals.get(&t.terminal_id.to_string());
                                let streamed = st.map(|s| s.streamed).unwrap_or(false);
                                let raw = st.map(|s| s.raw.clone()).unwrap_or_default();
                                let command =
                                    st.and_then(|s| s.command.clone()).unwrap_or_default();
                                let header_printed =
                                    st.map(|s| s.header_printed).unwrap_or(false);
                                exit_code = st.and_then(|s| s.exit_code);
                                if streamed {
                                    // Raw PTY bytes already live-written (full
                                    // color, unboxed) — newline, then close the
                                    // box below.
                                    let _ = writeln!(out);
                                } else if !raw.is_empty() {
                                    let _ = writeln!(out);
                                    render_terminal_emulated(
                                        out,
                                        &raw,
                                        &command,
                                        header_printed,
                                        color,
                                    );
                                }
                            }
                            _ => {}
                        }
                    }
                } else if let Some(raw) = mu_ref(&tc.raw_output) {
                    if let Some(result) = raw.get("result").and_then(|v| v.as_str()) {
                        let _ = writeln!(
                            out,
                            "{color}│{RESET} {DIM}{}{RESET}",
                            truncate(result, 200)
                        );
                    }
                }

                // Box bottom (12.1): ✓ green, ✗ red on non-zero exit.
                let (mark, label) = if is_terminal && exit_code.is_some_and(|c| c != 0) {
                    (BOLD_RED, format!("✗ exit {}", exit_code.unwrap()))
                } else if is_terminal {
                    (BOLD_GREEN, format!("✓ exit {}", exit_code.unwrap_or(0)))
                } else {
                    (BOLD_GREEN, "✓".to_string())
                };
                let _ = writeln!(
                    out,
                    "{color}└─ {mark}{label}{RESET} {color}─────────────────────────{RESET}"
                );

                self.tools.remove(&id);
            }

            Some(acp::ToolCallStatus::Failed) => {
                let state = self.tools.get(&id);
                let kind = state
                    .and_then(|s| s.kind.clone())
                    .or_else(|| mu_ref(&tc.kind).cloned());
                let color = tool_color(kind.as_ref());
                if state.is_none() {
                    // Never saw Pending (e.g. a call cancelled before it
                    // started): open the box late so the ✗ has a frame.
                    let icon = tool_icon(kind.as_ref());
                    let title = mu_ref(&tc.title).map(|s| s.as_str()).unwrap_or("tool");
                    let _ = writeln!(out, "{color}┌─ {icon} {title} ──────{RESET}");
                }
                let err = mu_ref(&tc.raw_output)
                    .and_then(|raw| raw.get("error").and_then(|v| v.as_str()))
                    .map(|e| truncate(e, 200))
                    .or_else(|| {
                        mu_ref(&tc.content).and_then(|content| {
                            content.iter().find_map(|item| match item {
                                acp::ToolCallContent::Content(boxed) => match &boxed.content {
                                    acp::ContentBlock::Text(t) => Some(truncate(&t.text, 200)),
                                    _ => None,
                                },
                                _ => None,
                            })
                        })
                    });
                match err {
                    Some(e) => {
                        let _ = writeln!(out, "{color}└─ {BOLD_RED}✗{RESET} {RED}{e}{RESET}");
                    }
                    None => {
                        let _ = writeln!(
                            out,
                            "{color}└─ {BOLD_RED}✗{RESET} {color}─────────────────────────{RESET}"
                        );
                    }
                }
                self.tools.remove(&id);
            }

            _ => {}
        }
    }
}

/// Render a complete markdown document (e.g. a list-command table, 12.6)
/// to stdout through the same streamdown pipeline as streamed agent text.
pub fn print_markdown(md: &str) {
    let mut r = CliRenderer::new();
    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    r.md_feed(&mut out, "list", md);
    r.md_finish(&mut out);
}

/// Render a git unified diff with colors. `bar` is the colored box side
/// (``│`` in the tool's kind color, already wrapped in RESET) prefixed to
/// every line so the diff stays inside the tool-call box.
fn render_diff(out: &mut impl Write, diff: &acp::Diff, bar: &str) {
    if let Some(patch) = &diff.patch {
        for line in patch.text.lines() {
            if line.starts_with("---") || line.starts_with("+++") {
                let _ = writeln!(out, "{bar} {BOLD}{}{RESET}", line);
            } else if line.starts_with("@@") {
                let _ = writeln!(out, "{bar} {CYAN}{}{RESET}", line);
            } else if line.starts_with('-') {
                let _ = writeln!(out, "{bar} {RED}{}{RESET}", line);
            } else if line.starts_with('+') {
                let _ = writeln!(out, "{bar} {GREEN}{}{RESET}", line);
            } else {
                let _ = writeln!(out, "{bar} {DIM}{}{RESET}", line);
            }
        }
    }

    for change in &diff.changes {
        let (op, path) = match &change.operation {
            acp::DiffChangeOperation::Modify(c) => ("modified", c.path.0.display().to_string()),
            acp::DiffChangeOperation::Add(c) => ("added", c.path.0.display().to_string()),
            acp::DiffChangeOperation::Delete(c) => ("deleted", c.path.0.display().to_string()),
            acp::DiffChangeOperation::Move(c) => ("moved", c.old_path.0.display().to_string()),
            acp::DiffChangeOperation::Copy(c) => ("copied", c.old_path.0.display().to_string()),
            _ => continue,
        };
        let _ = writeln!(out, "{bar} {DIM}{} {}{RESET}", op, path);
    }
}

fn decode_b64(data: &str) -> Vec<u8> {
    use base64::Engine;
    base64::engine::general_purpose::STANDARD
        .decode(data)
        .unwrap_or_default()
}

/// Render raw terminal bytes through a real alacritty terminal emulation,
/// re-emitting the resulting grid as ANSI. This interprets escapes, cursor
/// moves, wrapping, colors — exactly what a terminal would show.
/// Emulate raw terminal bytes through alacritty and re-emit the grid as ANSI
/// inside the tool-call box (12.1). Prints the box header (when not already
/// printed at Pending) and the `│` output lines; the CALLER prints the `└─`
/// footer with the ✓/✗ exit status.
fn render_terminal_emulated(
    out: &mut impl Write,
    raw: &[u8],
    command: &str,
    header_printed: bool,
    color: &str,
) {
    use alacritty_terminal::event::VoidListener;
    use alacritty_terminal::grid::Dimensions;
    use alacritty_terminal::term::{Config as TermConfig, Term};
    use alacritty_terminal::term::cell::Flags;
    use alacritty_terminal::vte::ansi::{Color, Processor};

    struct TermSize {
        lines: usize,
        cols: usize,
    }
    impl Dimensions for TermSize {
        fn total_lines(&self) -> usize {
            self.lines
        }
        fn screen_lines(&self) -> usize {
            self.lines
        }
        fn columns(&self) -> usize {
            self.cols
        }
    }

    let bounds = TermSize { lines: 50, cols: 120 };
    let mut config = TermConfig::default();
    config.scrolling_history = 100_000;
    let mut term: Term<VoidListener> = Term::new(config, &bounds, VoidListener);
    let mut processor: Processor<alacritty_terminal::vte::ansi::StdSyncHandler> =
        Processor::new();
    processor.advance(&mut term, raw);

    // Collect grid (history + screen) into lines of (fg, bg, char).
    let mut lines: Vec<Vec<(Color, Color, char)>> = Vec::new();
    let mut last_line = None;
    for indexed in term.grid().display_iter() {
        let cell = indexed.cell;
        if cell.flags.contains(Flags::WIDE_CHAR_SPACER) {
            continue;
        }
        let line_idx = indexed.point.line.0;
        if last_line != Some(line_idx) {
            lines.push(Vec::new());
            last_line = Some(line_idx);
        }
        lines.last_mut().unwrap().push((cell.fg, cell.bg, cell.c));
    }

    // Drop fully-blank trailing lines, cap display length (keep the tail).
    while lines
        .last()
        .is_some_and(|l| l.iter().all(|(_, _, c)| *c == ' '))
    {
        lines.pop();
    }
    let max_lines = 200;
    let skipped = lines.len().saturating_sub(max_lines);
    let display = &lines[skipped..];

    // Header box: already printed at Pending for the streaming path.
    if !header_printed {
        let _ = writeln!(out, "{color}┌─ ⚡ terminal ──────{RESET}");
        let header = if command.is_empty() {
            String::new()
        } else {
            format!("$ {command}")
        };
        let mut lines = header.lines();
        if let Some(first) = lines.next() {
            let _ = writeln!(out, "{color}│{RESET} {DIM}{first}{RESET}");
            for line in lines {
                let _ = writeln!(out, "{color}│{RESET} {DIM}  {line}{RESET}");
            }
        }
    }
    if skipped > 0 {
        let _ = writeln!(out, "{color}│{RESET} {DIM}… {skipped} earlier lines{RESET}");
    }

    let mut cur_fg: Option<Color> = None;
    let mut cur_bg: Option<Color> = None;
    for line in display {
        // Skip trailing blank cells so dim/box styling stays clean.
        let end = line
            .iter()
            .rposition(|(_, _, c)| *c != ' ')
            .map(|i| i + 1)
            .unwrap_or(0);
        let mut buf = format!("{color}│{RESET} ");
        for (fg, bg, c) in &line[..end] {
            if Some(*bg) != cur_bg {
                buf.push_str(&bg_code(bg));
                cur_bg = Some(*bg);
            }
            if Some(*fg) != cur_fg {
                buf.push_str(&fg_code(fg));
                cur_fg = Some(*fg);
            }
            buf.push(*c);
        }
        buf.push_str(RESET);
        cur_fg = None;
        cur_bg = None;
        let _ = writeln!(out, "{buf}");
    }
}

fn fg_code(c: &alacritty_terminal::vte::ansi::Color) -> String {
    color_code(c, 30, 38, 39)
}

fn bg_code(c: &alacritty_terminal::vte::ansi::Color) -> String {
    color_code(c, 40, 48, 49)
}

/// Build an ANSI escape for a color. `base` = 30/40 for named colors,
/// `ext` = 38/48 for indexed/rgb, `default` = 39/49.
///
/// NOTE: match by variant, never `as u8` — NamedColor::Foreground = 256,
/// which truncates to 0 (Black).
fn color_code(c: &alacritty_terminal::vte::ansi::Color, base: u8, ext: u8, default: u8) -> String {
    use alacritty_terminal::vte::ansi::{Color, NamedColor as N};
    match c {
        Color::Named(n) => {
            let code = match n {
                N::Black => base,
                N::Red => base + 1,
                N::Green => base + 2,
                N::Yellow => base + 3,
                N::Blue => base + 4,
                N::Magenta => base + 5,
                N::Cyan => base + 6,
                N::White => base + 7,
                N::BrightBlack => base + 60,
                N::BrightRed => base + 61,
                N::BrightGreen => base + 62,
                N::BrightYellow => base + 63,
                N::BrightBlue => base + 64,
                N::BrightMagenta => base + 65,
                N::BrightCyan => base + 66,
                N::BrightWhite => base + 67,
                N::DimBlack => base,
                N::DimRed => base + 1,
                N::DimGreen => base + 2,
                N::DimYellow => base + 3,
                N::DimBlue => base + 4,
                N::DimMagenta => base + 5,
                N::DimCyan => base + 6,
                N::DimWhite => base + 7,
                // Foreground/Background/Cursor/BrightForeground/DimForeground → default
                _ => return format!("\x1b[{default}m"),
            };
            format!("\x1b[{code}m")
        }
        Color::Indexed(i) => format!("\x1b[{ext};5;{i}m"),
        Color::Spec(rgb) => format!("\x1b[{ext};2;{};{};{}m", rgb.r, rgb.g, rgb.b),
    }
}

fn truncate(s: &str, max: usize) -> String {
    let s = s.trim();
    if s.len() <= max {
        s.to_string()
    } else {
        let mut end = max;
        while !s.is_char_boundary(end) {
            end -= 1;
        }
        format!("{}…", &s[..end])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_never_slices_mid_char() {
        // '→' is 3 bytes; a max landing inside it must back up to a boundary.
        let s = format!("{}←→", "a".repeat(198)); // ← at 198..201, → at 201..204
        assert_eq!(truncate(&s, 202), format!("{}←…", "a".repeat(198)));
        assert_eq!(truncate(&s, 200), format!("{}…", "a".repeat(198)));
        // Emoji (4 bytes) straddling the boundary.
        let s = format!("{}🦉", "x".repeat(199));
        assert_eq!(truncate(&s, 200), format!("{}…", "x".repeat(199)));
        // No truncation when under the limit.
        assert_eq!(truncate("héllo", 200), "héllo");
    }

    #[test]
    fn terminal_emulation_renders_ansi_from_raw_bytes() {
        // Raw PTY bytes: colored output via SGR escapes.
        let raw = b"plain \x1b[1;31mRED\x1b[0m \x1b[32mgreen\x1b[0m\r\n";
        let mut buf: Vec<u8> = Vec::new();
        render_terminal_emulated(&mut buf, raw, "test", false, GREEN);
        let out = String::from_utf8(buf).unwrap();

        assert!(out.contains("$ test"), "header shows command: {out:?}");
        assert!(out.contains("\x1b[31mRED"), "red fg preserved: {out:?}");
        assert!(out.contains("\x1b[32mgreen"), "green fg preserved: {out:?}");
        // Default fg/bg must use 39/49, never leak Named(Foreground=256) as Black.
        assert!(!out.contains("\x1b[30m"), "no black-fg leak: {out:?}");
        assert!(!out.contains("\x1b[41m"), "no red-bg leak: {out:?}");
    }

    #[test]
    fn terminal_header_never_truncated() {
        let raw = b"out\r\n";
        // Long single-line command: must appear in full, no ellipsis.
        let long = format!("echo {}", "x".repeat(200));
        let mut buf: Vec<u8> = Vec::new();
        render_terminal_emulated(&mut buf, raw, &long, false, GREEN);
        let out = String::from_utf8(buf).unwrap();
        assert!(out.contains(&format!("$ {long}")), "full command: {out:?}");
        assert!(!out.contains('…'), "no ellipsis: {out:?}");

        // Multi-line command: continuation lines under the box.
        let mut buf: Vec<u8> = Vec::new();
        render_terminal_emulated(&mut buf, raw, "line1\nline2", false, GREEN);
        let out = String::from_utf8(buf).unwrap();
        assert!(out.contains("$ line1"), "first line: {out:?}");
        assert!(out.contains("line2"), "second line: {out:?}");

        // Header already printed at Pending → no header re-render.
        let mut buf: Vec<u8> = Vec::new();
        render_terminal_emulated(&mut buf, raw, &long, true, GREEN);
        let out = String::from_utf8(buf).unwrap();
        assert!(!out.contains("┌─"), "header suppressed: {out:?}");
    }

    #[test]
    fn thought_brain_and_response_divider() {
        let mut r = CliRenderer::new();
        let mut buf: Vec<u8> = Vec::new();

        // Thinking phase: brain above the thinking content.
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::AgentThoughtChunk(acp::ContentChunk::new(
                acp::ContentBlock::Text(acp::TextContent::new("let me think")),
                "thought_1",
            )),
        );
        // Same phase continues: no second brain.
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::AgentThoughtChunk(acp::ContentChunk::new(
                acp::ContentBlock::Text(acp::TextContent::new(" some more")),
                "thought_1",
            )),
        );
        // The actual response: markdown --- divider between thought and answer.
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk::new(
                acp::ContentBlock::Text(acp::TextContent::new("here is my answer")),
                "msg_1",
            )),
        );
        // Idle finalizes the streamed document (as in live flow).
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(
                acp::IdleStateUpdate::default(),
            )),
        );

        let out = String::from_utf8(buf).unwrap();
        let brain = out
            .find('🧠')
            .unwrap_or_else(|| panic!("brain rendered: {out:?}"));
        let thought = out.find("let me think").expect("thought rendered");
        let divider = out
            .find("─".repeat(10).as_str())
            .unwrap_or_else(|| panic!("hr divider rendered: {out:?}"));
        let answer = out.find("here is my answer").expect("answer rendered");
        assert!(brain < thought, "brain above thinking: {out:?}");
        assert!(thought < divider, "divider after thinking: {out:?}");
        assert!(divider < answer, "divider before response: {out:?}");
        assert_eq!(out.matches('🧠').count(), 1, "one brain per phase: {out:?}");
    }

    #[test]
    fn no_brain_no_divider_without_thought() {
        let mut r = CliRenderer::new();
        let mut buf: Vec<u8> = Vec::new();
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::AgentMessageChunk(acp::ContentChunk::new(
                acp::ContentBlock::Text(acp::TextContent::new("straight answer")),
                "msg_1",
            )),
        );
        r.handle_update_to(
            &mut buf,
            &acp::SessionUpdate::StateUpdate(acp::StateUpdate::Idle(
                acp::IdleStateUpdate::default(),
            )),
        );
        let out = String::from_utf8(buf).unwrap();
        assert!(!out.contains('🧠'), "no brain: {out:?}");
        assert!(!out.contains("─".repeat(10).as_str()), "no divider: {out:?}");
        assert!(out.contains("straight answer"));
    }

    #[test]
    fn tool_call_box_lifecycle_non_terminal() {
        // 12.1: every tool call renders as a colored box — top at Pending,
        // content behind │, ✓ footer at Completed.
        let mut r = CliRenderer::new();
        let mut buf: Vec<u8> = Vec::new();

        let pending = acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new("call_1")
                .title("read(...)")
                .kind(acp::ToolKind::Read)
                .status(acp::ToolCallStatus::Pending),
        );
        r.handle_update_to(&mut buf, &pending);
        let completed = acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new("call_1")
                .status(acp::ToolCallStatus::Completed)
                .content(vec![acp::ToolCallContent::from(acp::ContentBlock::Text(
                    acp::TextContent::new("file contents here"),
                ))]),
        );
        r.handle_update_to(&mut buf, &completed);

        let out = String::from_utf8(buf).unwrap();
        assert!(out.contains("┌─ 📖 read(...)"), "box top: {out:?}");
        assert!(out.contains("file contents here"), "content: {out:?}");
        assert!(out.contains("└─"), "box bottom: {out:?}");
        assert!(out.contains("✓"), "check mark: {out:?}");
        assert!(out.contains("\x1b[36m"), "read box is cyan: {out:?}");
    }

    #[test]
    fn tool_call_box_failed_without_pending() {
        // A call cancelled before it started gets ONE Failed update (no
        // Pending) — it must still render a complete box, not a bare ✗.
        let mut r = CliRenderer::new();
        let mut buf: Vec<u8> = Vec::new();

        let failed = acp::SessionUpdate::ToolCallUpdate(
            acp::ToolCallUpdate::new("call_9")
                .title("terminal(...)")
                .kind(acp::ToolKind::Execute)
                .status(acp::ToolCallStatus::Failed)
                .content(vec![acp::ToolCallContent::from(acp::ContentBlock::Text(
                    acp::TextContent::new("cancelled"),
                ))]),
        );
        r.handle_update_to(&mut buf, &failed);

        let out = String::from_utf8(buf).unwrap();
        assert!(out.contains("┌─ ⚡ terminal(...)"), "box top: {out:?}");
        assert!(out.contains("└─"), "box bottom: {out:?}");
        assert!(out.contains("✗"), "cross: {out:?}");
        assert!(out.contains("cancelled"), "reason: {out:?}");
    }
}

#[test]
fn print_markdown_table_smoke() {
    print_markdown("| A | B |\n|---|---|\n| 1 | 2 |\n\ncaption line");
}

//! The diff card: textual-diff-view's unified view as transcript lines.

use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

use crate::events::ToolDiff;

use super::layout::{self, Options, Row, Syntax};
use super::pipeline;
use super::pipeline::Group;

/// One diff, ready to render: the two sides' lines and the change geometry.
pub struct Diff {
    pub path: String,
    pub a: Vec<String>,
    pub b: Vec<String>,
    pub groups: Vec<Group>,
}

impl Diff {
    /// An ACP v2 `git_patch`: hunks only, one group per hunk.
    pub fn from_patch(path: &str, patch: &str) -> Diff {
        let p = super::patch::parse(patch);
        Diff {
            path: path.to_string(),
            a: p.a,
            b: p.b,
            groups: p.groups,
        }
    }

    /// Whole texts on both sides (ACP v1 `oldText`/`newText`): the line-level
    /// matcher over the real files, exactly as the Python widget diffs them.
    pub fn from_texts(path: &str, old: &str, new: &str) -> Diff {
        let a: Vec<&str> = old.lines().collect();
        let b: Vec<&str> = new.lines().collect();
        let groups = pipeline::diff(&a, &b);
        Diff {
            path: path.to_string(),
            a: a.iter().map(|s| s.to_string()).collect(),
            b: b.iter().map(|s| s.to_string()).collect(),
            groups,
        }
    }

    /// A tool call's diff block. v2 hands over the patch the agent computed;
    /// v1 handed over both whole texts and left the diffing to us. A file that
    /// did not exist arrives with no old side at all, which reads as an add.
    pub fn from_tool_diff(tool_diff: &ToolDiff) -> Diff {
        match &tool_diff.patch {
            Some(patch) => Diff::from_patch(&tool_diff.path, patch),
            None => Diff::from_texts(
                &tool_diff.path,
                tool_diff.old_text.as_deref().unwrap_or_default(),
                tool_diff.new_text.as_deref().unwrap_or_default(),
            ),
        }
    }

    /// `(additions, removals)`, the title's `(+N, -M)`.
    pub fn counts(&self) -> (usize, usize) {
        pipeline::counts(&self.groups)
    }

    /// The card's `📄 path (+N, -M)` title on its own: the collapsed card,
    /// which is the whole change summarized in one row.
    pub fn title_lines(&self, width: usize) -> Vec<Line<'static>> {
        let (add, rem) = self.counts();
        layout::title_rows(&self.path, add, rem, width)
            .iter()
            .map(row_line)
            .collect()
    }

    /// The unified view at `width`, long lines folded, as transcript lines.
    pub fn lines(&self, width: usize) -> Vec<Line<'static>> {
        let a: Vec<&str> = self.a.iter().map(String::as_str).collect();
        let b: Vec<&str> = self.b.iter().map(String::as_str).collect();
        let inline = pipeline::inline_marks(&a, &b, &self.groups);
        let syntax = Syntax::plain(a.len(), b.len());
        let opts = Options {
            width,
            annotations: false,
            wrap: true,
            path: self.path.clone(),
            inline: &inline,
            syntax: &syntax,
        };
        layout::unified(&a, &b, &self.groups, &opts)
            .iter()
            .map(row_line)
            .collect()
    }
}

fn style_of(c: &layout::Cell) -> Style {
    let mut s = Style::default().bg(Color::Rgb(c.bg.0, c.bg.1, c.bg.2));
    s = match c.fg {
        Some((r, g, b)) => s.fg(Color::Rgb(r, g, b)),
        None => s.fg(Color::Reset),
    };
    if c.bold {
        s = s.add_modifier(Modifier::BOLD);
    }
    if c.italic {
        s = s.add_modifier(Modifier::ITALIC);
    }
    if c.underline {
        s = s.add_modifier(Modifier::UNDERLINED);
    }
    s
}

/// One layout row to one transcript line: consecutive columns sharing a style
/// collapse into a span, and a wide character's stub column -- the half the
/// glyph itself covers -- is dropped, because ratatui advances over it.
fn row_line(row: &Row) -> Line<'static> {
    let mut spans: Vec<Span<'static>> = Vec::new();
    let mut run: Option<(Style, String)> = None;
    for c in row {
        if c.stub {
            continue;
        }
        let style = style_of(c);
        match &mut run {
            Some((s, text)) if *s == style => text.push(c.ch),
            _ => {
                if let Some((s, text)) = run.take() {
                    spans.push(Span::styled(text, s));
                }
                run = Some((style, c.ch.to_string()));
            }
        }
    }
    if let Some((s, text)) = run {
        spans.push(Span::styled(text, s));
    }
    Line::from(spans)
}

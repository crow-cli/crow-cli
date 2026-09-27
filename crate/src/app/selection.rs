//! selection: extracted verbatim from src/app.rs (Phase 1 split).

/// One endpoint of a mouse selection in chat-layout coordinates: `line`
/// indexes the full wrapped layout (`ChatView::lines`), `col` is a display
/// cell column within the chat pane.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct SelPoint {
    pub line: usize,
    pub col: usize,
}

/// In-app mouse selection — the grok-build gesture: drag highlights,
/// releasing the button copies (选中完即 copy). `anchor` is where the drag
/// started; `head` follows the pointer and may precede the anchor.
#[derive(Clone, Copy, Debug)]
pub struct Selection {
    pub anchor: SelPoint,
    pub head: SelPoint,
}

impl Selection {
    /// (start, end) in document order; `end` is inclusive (the cell under
    /// the pointer is part of the selection).
    pub fn ordered(&self) -> (SelPoint, SelPoint) {
        if (self.head.line, self.head.col) < (self.anchor.line, self.anchor.col) {
            (self.head, self.anchor)
        } else {
            (self.anchor, self.head)
        }
    }

    pub(crate) fn is_caret(&self) -> bool {
        self.anchor == self.head
    }
}

/// Composer drag-selection (same gesture as the chat pane): both endpoints
/// are cells in the input text-area coordinates — `(row, col)` where the
/// drag began and where the pointer is now. The covered char range is
/// derived with [`App::input_selection_range`], which treats both endpoint
/// cells as inclusive so either drag direction selects exactly the cells
/// the pointer crossed.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct InputSel {
    pub anchor: (usize, usize),
    pub head: (usize, usize),
}

/// Snapshot of the chat pane layout from the last draw — the seam that
/// mouse hit-testing and copy extraction read (grok-build's resolved
/// selection model, scaled way down): pane rect, index of the first
/// visible layout line, and the plain text of every layout line.
/// A thumbnail the terminal should draw over the chat pane (kitty graphics).
pub struct ThumbPlacement {
    pub id: u32,
    pub rect: ratatui::layout::Rect,
    pub data: std::sync::Arc<[u8]>,
}

#[derive(Default)]
pub struct ChatView {
    pub area: ratatui::layout::Rect,
    pub top: usize,
    /// Absolute top line while the user explores scrollback. `None` follows
    /// the streaming tail; a scroll gesture is resolved into a fresh anchor
    /// by the next draw.
    pub(crate) manual_top: Option<usize>,
    /// The frame's selection snapshot, **viewport-sized**: the plain text of
    /// the `top..top+len` layout lines this frame actually showed (L25 —
    /// hit-testing and copy extraction never need more). `total` carries the
    /// absolute line count for scroll math.
    pub lines: Vec<String>,
    /// Per snapshot line (same viewport window), the transcript cell that
    /// owns it (only tool cells claim ownership) — the seam for
    /// click-to-expand.
    pub owners: Vec<Option<usize>>,
    /// Total layout line count of the last frame (viewport-relative lines
    /// exist only for `top..top+lines.len()`).
    pub total: usize,
    /// Visible image thumbnails, filled by `ui::draw_chat` every frame.
    pub images: Vec<ThumbPlacement>,
}

impl ChatView {
    /// The frame's snapshot text for an absolute layout line — `None`
    /// outside the viewport this frame captured.
    pub fn line_text(&self, line: usize) -> Option<&str> {
        self.lines.get(line.checked_sub(self.top)?).map(String::as_str)
    }

    /// The transcript cell owning an absolute layout line — `None` outside
    /// the viewport or for lines no tool cell owns.
    pub fn line_owner(&self, line: usize) -> Option<usize> {
        self.owners.get(line.checked_sub(self.top)?).copied().flatten()
    }
}

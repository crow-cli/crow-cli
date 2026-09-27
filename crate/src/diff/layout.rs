//! Row layout for the diff view: unified and split.
//!
//! A port of `DiffView._compose_unified`, `DiffView._compose_split`,
//! `DiffView.get_title` and Textual's word wrapper. Pure: rows of plain cells
//! out, no ratatui anywhere, so the geometry is testable without a screen and
//! identical between a unit test and the live pane.
//!
//! Unified column arithmetic, with `W` the widest line number in the group:
//!
//!   col1  "▎" + f"{n:>W}" + " "    W+2 cells   cell 0 edge, 1.. number
//!   col2  " " + f"{n:>W}" + " "    W+2 cells   all number
//!   col3  " {ann} " or blank(1)    3 or 1      line bg + annotation fg
//!   col4  code                     the rest    line bg + syntax fg
//!
//! Split repeats `numbers | annotation | code` twice. Both code columns are
//! `DiffCode { width: auto; min-width: 1fr }`, so Textual's solver hands them
//! the leftover equally and gives the odd cell to the RIGHT one:
//!
//!   remaining = width - 2 * ((W + 2) + ann_w)
//!   code_a = remaining / 2 (floored)      code_b = remaining - code_a
//!
//! At `remaining == 0` both fall back to a minimal width of 1 and overflow; at
//! `remaining == 1` the `1fr` unit is `1/2`, `get_content_height` is asked for
//! `int(1/2)` columns and returns 0, so both containers are zero rows tall and
//! paint nothing but the group background.

use unicode_width::UnicodeWidthChar;

use crate::diff::pipeline::{op_tuple, Group, Inline};
use crate::diff::theme::{
    annotation_fg, auto_text, blend, code_bg, edge_bg, edge_fg, group_bg, inherit, line_styles,
    number_bg, number_fg, rgba, Rgb, Rgba, Role, APP_BG, INLINE_ADDED_BG, INLINE_REMOVED_BG, TEXT,
    TEXT_DIM, TEXT_ERROR, TEXT_PRIMARY, TEXT_SUCCESS, TITLE_BORDER,
};

/// Which file an output row's code came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Side {
    A,
    B,
}

impl Side {
    /// The annotation this side's marker column highlights -- `-` for the
    /// original, `+` for the modified.
    fn highlight(self) -> char {
        match self {
            Side::A => '-',
            Side::B => '+',
        }
    }
}

/// One character's syntax style, as Textual resolves a highlight span.
///
/// Colors keep their alpha: `$text-success 80%` is not a color, it is
/// composited over whatever background the cell ends up with, so the same span
/// renders differently on an added line than on an unchanged one. An `auto`
/// foreground (`$text`) arrives already resolved to its contrast color, which
/// is white for every background this view produces.
///
/// `None` means the span set nothing, so whatever is underneath shows through.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Sym {
    pub fg: Option<Rgba>,
    pub bg: Option<Rgba>,
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
}

impl Sym {
    /// `$text`, undecorated -- what an unhighlighted character gets.
    pub const PLAIN: Sym = Sym {
        fg: Some(rgba(255, 255, 255, 1.0)),
        bg: None,
        bold: false,
        italic: false,
        underline: false,
    };
}

/// Syntax styles by file line, one table per side. A line missing from the
/// table, or an entry shorter than the line, falls back to `Sym::PLAIN`.
#[derive(Clone, Debug)]
pub struct Syntax {
    pub a: Vec<Vec<Sym>>,
    pub b: Vec<Vec<Sym>>,
}

impl Syntax {
    pub fn plain(a: usize, b: usize) -> Syntax {
        Syntax { a: vec![Vec::new(); a], b: vec![Vec::new(); b] }
    }

    fn side(&self, s: Side) -> &[Vec<Sym>] {
        match s {
            Side::A => &self.a,
            Side::B => &self.b,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Cell {
    pub ch: char,
    /// None means "leave the terminal default", which is what Textual emits for
    /// the title row's padding and nothing else.
    pub fg: Option<Rgb>,
    pub bg: Rgb,
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
    /// The second column of the double-width character before it. The terminal
    /// makes this cell itself, so the renderer records it but never writes it.
    pub stub: bool,
}

pub type Row = Vec<Cell>;

pub struct Options<'o> {
    pub width: usize,
    pub annotations: bool,
    /// Fold long code lines instead of clipping them: `_compose_*_wrap`.
    pub wrap: bool,
    pub path: String,
    pub inline: &'o Inline,
    pub syntax: &'o Syntax,
}

impl<'o> Options<'o> {
    pub fn new(width: usize, path: &str, inline: &'o Inline, syntax: &'o Syntax) -> Options<'o> {
        Options { width, annotations: false, wrap: false, path: path.to_string(), inline, syntax }
    }
}

// ---- cell metrics ---------------------------------------------------------

/// rich's `get_character_cell_size`: 2 for wide/fullwidth, 0 for combining and
/// control characters, 1 for everything else. Ambiguous-width glyphs -- `▎`,
/// `╲`, `⋮`, `╍` -- are 1, which is what both Textual and pyte use.
pub fn cell_width(ch: char) -> usize {
    ch.width().unwrap_or(0)
}

pub fn row_width(row: &[Cell]) -> usize {
    row.iter().map(|c| cell_width(c.ch)).sum()
}

/// `Content.cell_length` for a source line.
fn text_cells(text: &str) -> usize {
    text.chars().map(cell_width).sum()
}

fn cell(ch: char, fg: Option<Rgb>, bg: Rgb) -> Cell {
    Cell { ch, fg, bg, bold: false, italic: false, underline: false, stub: false }
}

/// Extend `row` with unstyled-background spaces until it occupies `width`
/// display cells. Counts cells, not characters, so a row containing `📄` stops
/// in the right place.
fn pad_cells(row: &mut Row, width: usize, fg: Option<Rgb>, bg: Rgb) {
    let mut acc = row_width(row);
    while acc < width {
        row.push(cell(' ', fg, bg));
        acc += 1;
    }
}

fn push_str(row: &mut Row, s: &str, fg: Option<Rgb>, bg: Rgb, bold: bool) {
    for ch in s.chars() {
        row.push(Cell { ch, fg, bg, bold, italic: false, underline: false, stub: false });
    }
}

// ---- word wrap ------------------------------------------------------------

fn cells(text: &[char]) -> i64 {
    text.iter().map(|c| cell_width(*c) as i64).sum()
}

/// `re_word = re.compile(r"\s*\S+\s*")`: leading whitespace, a word, and any
/// whitespace to its right. `None` when no word is left, so a trailing
/// whitespace-only tail is never yielded.
fn word_at(text: &[char], i: usize) -> Option<(usize, usize)> {
    let mut j = i;
    while j < text.len() && text[j].is_whitespace() {
        j += 1;
    }
    let word_start = j;
    while j < text.len() && !text[j].is_whitespace() {
        j += 1;
    }
    if j == word_start {
        return None;
    }
    while j < text.len() && text[j].is_whitespace() {
        j += 1;
    }
    Some((i, j))
}

/// `cell_len(word.rstrip())`: the width the fit test measures, which excludes
/// the trailing whitespace the advance then charges for anyway.
fn rstrip_cells(word: &[char]) -> i64 {
    let mut end = word.len();
    while end > 0 && word[end - 1].is_whitespace() {
        end -= 1;
    }
    cells(&word[..end])
}

/// `rich.cells.chop_cells`: cut `text` into lines of at most `width` cells.
///
/// rich walks grapheme clusters; this walks codepoints, which differs only for
/// combining marks -- and a title has none.
fn chop_cells(text: &[char], width: i64) -> Vec<Vec<char>> {
    let width = width.max(1) as usize;
    let mut lines: Vec<Vec<char>> = Vec::new();
    let mut line: Vec<char> = Vec::new();
    let mut line_size = 0usize;
    for &ch in text {
        let cw = cell_width(ch);
        if line_size + cw > width {
            lines.push(std::mem::take(&mut line));
            line_size = 0;
        }
        line.push(ch);
        line_size += cw;
    }
    if line_size > 0 {
        lines.push(line);
    }
    lines
}

/// Port of `rich._wrap.divide_line`, which is what `Content.wrap` calls --
/// NOT `textual._wrap.compute_wrap_offsets`, whose chunking and fit test both
/// differ. Returns the codepoint offsets to break `text` at.
///
/// Two details make this not the obvious greedy wrapper. The fit test measures
/// the word with its trailing whitespace stripped while the advance includes
/// it, so `cell_offset` can run past `width` and `remaining_space` go negative
/// (hence the signed type). And a word that fits on no line is folded, with a
/// break emitted at the start of every folded line including the last.
pub fn divide_line(text: &[char], width: i64, fold: bool) -> Vec<usize> {
    let mut breaks: Vec<usize> = Vec::new();
    let mut cell_offset: i64 = 0;
    let mut i = 0usize;
    while let Some((start, end)) = word_at(text, i) {
        let word = &text[start..end];
        let word_length = rstrip_cells(word);
        if width - cell_offset >= word_length {
            cell_offset += cells(word);
        } else if word_length > width {
            if fold {
                let folded = chop_cells(word, width);
                let last = folded.len().saturating_sub(1);
                let mut cur = start;
                for (k, line) in folded.iter().enumerate() {
                    if cur != 0 {
                        breaks.push(cur);
                    }
                    if k == last {
                        cell_offset = cells(line);
                    } else {
                        cur += line.len();
                    }
                }
            } else {
                if start != 0 {
                    breaks.push(start);
                }
                cell_offset = cells(word);
            }
        } else if cell_offset != 0 && start != 0 {
            // It does not fit here, but it does fit on a fresh line.
            breaks.push(start);
            cell_offset = cells(word);
        }
        i = end;
    }
    breaks
}

/// `Content.rstrip()`: drop trailing whitespace.
fn rstrip_row(row: &mut Row) {
    while row.last().is_some_and(|c| c.ch.is_whitespace()) {
        row.pop();
    }
}

/// `Content.truncate(width, ellipsis=False)`, i.e. rich's `set_cell_size`: cut
/// to `width` cells, and when a double-width character straddles the cut, leave
/// a space in its place rather than dropping the cell.
fn truncate_cells(row: &mut Row, width: usize) {
    let mut acc = 0usize;
    for i in 0..row.len() {
        let cw = cell_width(row[i].ch);
        if acc + cw > width {
            // `set_cell_size` swaps the straddling character for a space and
            // `_trim_spans` keeps the spans where they were, so the space still
            // wears that character's style.
            let blank = Cell { ch: ' ', ..row[i] };
            row.truncate(i);
            if acc < width {
                row.push(blank);
            }
            return;
        }
        acc += cw;
    }
}

// ---- screen columns -------------------------------------------------------

/// A row of `width` columns with nothing painted on it: the app background and
/// no foreground, which is what the widget leaves where it draws nothing.
fn blank_columns(width: usize) -> Row {
    vec![cell(' ', None, APP_BG); width]
}

/// One terminal write run: `run` starting at column `start`.
///
/// Textual turns DECAWM off, so a run that reaches the right edge does not wrap.
/// pyte parks the cursor one past the last column and then backs it up by the
/// width of whatever arrives next, so the overflow overwrites the cells already
/// there -- a narrow character lands on the last column, a double-width one on
/// the last two. Everything is clamped to the screen; nothing wraps.
///
/// A double-width character also gets the blank stub the terminal gives it,
/// wearing its own style, so the row that comes out has exactly one cell per
/// column and can be blitted straight into a buffer.
fn write_run(out: &mut Row, run: &[Cell], start: usize, width: usize) {
    let limit = width as i64;
    let mut cursor = start as i64;
    for c in run {
        let w = cell_width(c.ch) as i64;
        if w == 0 {
            continue;
        }
        if cursor == limit {
            cursor -= w;
        }
        if (0..limit).contains(&cursor) {
            out[cursor as usize] = *c;
            if w == 2 && cursor + 1 < limit {
                out[cursor as usize + 1] = Cell { ch: ' ', stub: true, ..*c };
            }
        }
        cursor = (cursor + w).min(limit);
    }
}

/// Expand a row into one cell per screen column.
pub fn columns(row: &[Cell], width: usize) -> Row {
    let mut out = blank_columns(width);
    write_run(&mut out, row, 0, width);
    out
}

/// `columns` for every row of a group.
fn columnize(rows: &[Row], width: usize) -> Vec<Row> {
    rows.iter().map(|r| columns(r, width)).collect()
}

// ---- title ----------------------------------------------------------------

/// `📄 path (+N, -N)`, per `get_title`'s markup, one cell-vector entry per
/// codepoint with its style already resolved.
fn title_cells(path: &str, additions: usize, removals: usize) -> Vec<Cell> {
    let bg = APP_BG;
    let mut v: Vec<Cell> = Vec::new();
    push_str(&mut v, "📄 ", Some(TEXT), bg, false);
    push_str(&mut v, path, Some(TEXT_DIM), bg, false);
    push_str(&mut v, " (", Some(TEXT), bg, false);
    push_str(&mut v, &format!("+{additions}"), Some(TEXT_SUCCESS), bg, true);
    push_str(&mut v, ", ", Some(TEXT), bg, false);
    push_str(&mut v, &format!("-{removals}"), Some(TEXT_ERROR), bg, true);
    push_str(&mut v, ")", Some(TEXT), bg, false);
    v
}

/// The title, word-wrapped to `width`.
///
/// Below its cell length the `.title` Static wraps and every row after it moves
/// down one, which matters for real paths long before it matters for narrow
/// terminals. `_wrap_and_format` divides at rich's `divide_line`, then `rstrip()`s
/// every line but the last -- that is why the space before a wrapped `-3)`
/// disappears -- and truncates each to the width. Padding past the text carries
/// no foreground at all.
pub fn title_rows(path: &str, additions: usize, removals: usize, width: usize) -> Vec<Row> {
    let full = title_cells(path, additions, removals);
    let chars: Vec<char> = full.iter().map(|c| c.ch).collect();
    let offsets = divide_line(&chars, width as i64, true);

    let mut bounds: Vec<usize> = Vec::with_capacity(offsets.len() + 2);
    bounds.push(0);
    bounds.extend(offsets);
    bounds.push(chars.len());

    let last = bounds.len() - 2;
    bounds
        .windows(2)
        .enumerate()
        .map(|(k, w)| {
            let mut piece: Row = full[w[0]..w[1]].to_vec();
            if k != last {
                rstrip_row(&mut piece);
            }
            truncate_cells(&mut piece, width);
            pad_cells(&mut piece, width, None, APP_BG);
            piece
        })
        .collect()
}

/// `.title { border-bottom: dashed $foreground 20% }`
pub fn border_row(width: usize) -> Row {
    let fg = blend(TITLE_BORDER, APP_BG);
    (0..width).map(|_| cell('╍', Some(fg), APP_BG)).collect()
}

// ---- folds ----------------------------------------------------------------

/// Where `Ellipsis("⋮")` puts its glyph in a `width: 1fr; text-align: center;
/// offset-x: -1` box: `(width - cell_length) / 2 - 1`, floored.
fn ellipsis_x(half: usize) -> usize {
    (half.saturating_sub(1) / 2).saturating_sub(1)
}

fn put_ellipsis(row: &mut Row, x: usize) {
    if x < row.len() {
        row[x] = Cell {
            ch: '⋮',
            fg: Some(TEXT_PRIMARY),
            bg: row[x].bg,
            bold: true,
            italic: false,
            underline: false,
            stub: false,
        };
    }
}

/// The unified view's single full-width fold.
pub fn ellipsis_row(width: usize) -> Row {
    let mut row: Row = Vec::new();
    pad_cells(&mut row, width, None, APP_BG);
    put_ellipsis(&mut row, ellipsis_x(width));
    row
}

/// The split view's fold: `_compose_split` yields TWO `Ellipsis` in a plain
/// (unclassed, so unbackgrounded) `HorizontalGroup`, one over each half.
pub fn split_ellipsis_row(width: usize) -> Row {
    let left = width / 2;
    let mut row: Row = Vec::new();
    pad_cells(&mut row, width, None, APP_BG);
    put_ellipsis(&mut row, ellipsis_x(left));
    put_ellipsis(&mut row, left + ellipsis_x(width - left));
    row
}

// ---- code column ----------------------------------------------------------

fn marks_for(inline: &Inline, s: Side, line: usize) -> &[bool] {
    let table = match s {
        Side::A => &inline.removed,
        Side::B => &inline.added,
    };
    table.get(line).map(Vec::as_slice).unwrap_or(&[])
}

/// Append `text` as diff code, filling exactly `avail` display cells.
///
/// Precedence is the span stack in `LineContent.render_strips` --
/// `line.stylize_before(color).stylize_before(style)` puts the widget base
/// first and the line's own spans last, so the inline highlight wins over a
/// syntax span's own background and the syntax foreground composites over
/// whatever background survives. Padding comes from `Content.pad_right`, which
/// leaves the spans alone, so it carries the line tint and `$text`.
fn emit_code(
    row: &mut Row,
    text: &[char],
    c_bg: Rgb,
    marks: &[bool],
    syms: &[Sym],
    inline_bg: Rgb,
    avail: usize,
) {
    let mut acc = 0usize;
    for (i, ch) in text.iter().copied().enumerate() {
        let sym = syms.get(i).copied().unwrap_or(Sym::PLAIN);
        // Precedence is the span stack in `LineContent.render_strips`: the
        // inline highlight replaces the line tint outright, and a syntax span's
        // own background composites over whatever tint survives.
        let bg = if marks.get(i).copied().unwrap_or(false) {
            inline_bg
        } else {
            match sym.bg {
                Some(c) => blend(c, c_bg),
                None => c_bg,
            }
        };
        let fg = match sym.fg {
            Some(c) => inherit(c, bg),
            None => auto_text(bg),
        };
        let styled = Cell {
            ch,
            fg: Some(fg),
            bg,
            bold: sym.bold,
            italic: sym.italic,
            underline: sym.underline,
            stub: false,
        };
        let cw = cell_width(ch);
        if acc + cw > avail {
            // Cropping through a double-width character leaves a space wearing
            // that character's style, not the base one.
            if acc < avail {
                row.push(Cell { ch: ' ', ..styled });
                acc += 1;
            }
            break;
        }
        row.push(styled);
        acc += cw;
    }
    while acc < avail {
        row.push(cell(' ', Some(TEXT), c_bg));
        acc += 1;
    }
}

fn code_cell(row: &mut Row, text: &str, side: Side, src: usize, ann: char, opts: &Options<'_>, avail: usize) {
    let role = Role::from_annotation(ann);
    let c_bg = code_bg(role);
    let marks = marks_for(opts.inline, side, src);
    let syms = opts.syntax.side(side).get(src).map(Vec::as_slice).unwrap_or(&[]);
    emit_code(row, &text.chars().collect::<Vec<_>>(), c_bg, marks, syms, inline_bg(side), avail);
}

/// The opaque inline-highlight background that replaces the line tint.
fn inline_bg(side: Side) -> Rgb {
    match side {
        Side::A => INLINE_REMOVED_BG,
        Side::B => INLINE_ADDED_BG,
    }
}

// ---- unified --------------------------------------------------------------

/// One output row's worth of source: the line number(s) it shows, its
/// annotation, and the code it renders. Shared by all four compose paths.
///
/// `code` is `None` for the hatch filler `fill_lists` pads the short side of a
/// split group with; `side` and `src` then mean nothing. `num_b` is the unified
/// view's second number column -- split shows one number per column and leaves
/// it `None`.
#[derive(Clone, Copy)]
struct Slot<'x> {
    num: Option<usize>,
    num_b: Option<usize>,
    ann: char,
    code: Option<&'x str>,
    side: Side,
    /// Index into the FILE, which is what the inline marks and the syntax
    /// tables are keyed by.
    src: usize,
}

impl Slot<'_> {
    fn hatch() -> Slot<'static> {
        Slot { num: None, num_b: None, ann: '/', code: None, side: Side::A, src: 0 }
    }

    /// The cell width of this slot's own code, 0 for a hatch filler.
    fn cell_len(&self) -> usize {
        self.code.map(text_cells).unwrap_or(0)
    }
}

/// `fill_lists`: make the two sides of a split group the same length by
/// extending the shorter one with the hatch filler.
fn fill_slots(a: &mut Vec<Slot<'_>>, b: &mut Vec<Slot<'_>>) {
    while a.len() < b.len() {
        a.push(Slot::hatch());
    }
    while b.len() < a.len() {
        b.push(Slot::hatch());
    }
}

/// `_compose_unified`'s collection pass: one slot per output row, in order.
/// A `replace` emits its a-side rows first, then its b-side rows.
fn unified_slots<'x>(a: &'x [&'x str], b: &'x [&'x str], g: &Group) -> Vec<Slot<'x>> {
    let mut out: Vec<Slot<'x>> = Vec::new();
    for o in &g.ops {
        let (tag, i1, i2, j1, j2) = op_tuple(o);
        match tag {
            "equal" => out.extend(a[i1..i2].iter().enumerate().map(|(k, line)| Slot {
                num: Some(i1 + k + 1),
                num_b: Some(j1 + k + 1),
                ann: ' ',
                code: Some(line),
                side: Side::A,
                src: i1 + k,
            })),
            "delete" | "replace" => {
                out.extend(a[i1..i2].iter().enumerate().map(|(k, line)| Slot {
                    num: Some(i1 + k + 1),
                    num_b: None,
                    ann: '-',
                    code: Some(line),
                    side: Side::A,
                    src: i1 + k,
                }));
                if tag == "replace" {
                    out.extend(b[j1..j2].iter().enumerate().map(|(k, line)| Slot {
                        num: None,
                        num_b: Some(j1 + k + 1),
                        ann: '+',
                        code: Some(line),
                        side: Side::B,
                        src: j1 + k,
                    }));
                }
            }
            "insert" => out.extend(b[j1..j2].iter().enumerate().map(|(k, line)| Slot {
                num: None,
                num_b: Some(j1 + k + 1),
                ann: '+',
                code: Some(line),
                side: Side::B,
                src: j1 + k,
            })),
            _ => {}
        }
    }
    out
}

/// One group's rows in the unfolded unified view.
fn group_rows(a: &[&str], b: &[&str], g: &Group, opts: &Options<'_>) -> Vec<Row> {
    let slots = unified_slots(a, b, g);
    let w = number_width(
        slots.iter().map(|s| s.num).chain(slots.iter().map(|s| s.num_b)),
        slots.is_empty(),
    );

    let mut rows = Vec::new();
    for s in &slots {
        let mut row: Row = Vec::new();
        emit_gutter(&mut row, s, Chrome::Unified { w }, opts);
        // col4: the code, out to the right edge
        let avail = opts.width.saturating_sub(row_width(&row));
        code_cell(&mut row, s.code.unwrap_or(""), s.side, s.src, s.ann, opts, avail);
        rows.push(row);
    }
    rows
}

/// `W`: the widest line number in the group, `None` counting as nothing.
/// `_compose_split` falls back to 1 when the group produced no rows at all.
fn number_width(nums: impl Iterator<Item = Option<usize>>, empty: bool) -> usize {
    if empty {
        return 1;
    }
    nums.map(|n| n.map(|v| v.to_string().len()).unwrap_or(0)).max().unwrap_or(1)
}

fn num_field(n: Option<usize>, w: usize) -> String {
    match n {
        Some(v) => format!("{v:>w$}"),
        None => " ".repeat(w),
    }
}

/// The whole unified view: title, dashed border, groups separated by folds.
pub fn unified(a: &[&str], b: &[&str], groups: &[Group], opts: &Options<'_>) -> Vec<Row> {
    let (add, rem) = crate::diff::pipeline::counts(groups);
    let mut rows = title_rows(&opts.path, add, rem, opts.width);
    rows.push(border_row(opts.width));
    for (i, g) in groups.iter().enumerate() {
        if i > 0 {
            rows.push(ellipsis_row(opts.width));
        }
        rows.extend(if opts.wrap {
            unified_wrap_group(a, b, g, opts)
        } else {
            group_rows(a, b, g, opts)
        });
    }
    columnize(&rows, opts.width)
}

// ---- split ----------------------------------------------------------------

/// `format_number`: `▎{n:>W} ` with the edge style on cell 0 and the number
/// style on the rest, or -- when there is no line here -- `╲` * (W + 2) in the
/// hatch style, which is the same width.
fn emit_numbers(row: &mut Row, s: &Slot<'_>, w: usize) {
    match s.num {
        None => {
            let fg = annotation_fg(Role::Hatch);
            let bg = group_bg();
            for _ in 0..w + 2 {
                row.push(cell('╲', Some(fg), bg));
            }
        }
        Some(n) => {
            let role = Role::from_annotation(s.ann);
            row.push(cell('▎', Some(edge_fg(role)), edge_bg(role)));
            push_str(
                row,
                &format!("{n:>w$} "),
                Some(number_fg(role)),
                number_bg(role),
                false,
            );
        }
    }
}

/// `make_annotation(annotation, highlight_annotation)`.
fn emit_annotation(row: &mut Row, ann: char, highlight: char, opts: &Options<'_>) {
    let role = Role::from_annotation(ann);
    if !opts.annotations {
        if ann == '/' {
            row.push(cell('╲', Some(annotation_fg(Role::Hatch)), group_bg()));
        } else {
            // `Content(" ").stylize(LINE_STYLES[ann])`: a transparent-fg line
            // style, which resolves to `$text`.
            let bg = code_bg(role);
            row.push(cell(' ', Some(inherit(line_styles(role).fg, bg)), bg));
        }
        return;
    }
    if ann == highlight {
        let bg = code_bg(role);
        let fg = annotation_fg(role);
        row.push(cell(' ', Some(fg), bg));
        row.push(cell(ann, Some(fg), bg));
        row.push(cell(' ', Some(fg), bg));
    } else if ann == '/' {
        let fg = annotation_fg(Role::Hatch);
        for _ in 0..3 {
            row.push(cell('╲', Some(fg), group_bg()));
        }
    } else {
        // `Content(" " * 3)` with no spans at all: the widget's own style over
        // the group background.
        for _ in 0..3 {
            row.push(cell(' ', Some(TEXT), group_bg()));
        }
    }
}

/// `_compose_split_wrap`'s own `make_annotation`.
///
/// The unfolded one stops at `LINE_STYLES` when annotations are off; the wrapped
/// one layers `ANNOTATION_STYLES` on top of it, so a changed line's marker column
/// wears the annotation color instead of `$text`. With annotations on the two are
/// the same function.
fn emit_annotation_wrap(row: &mut Row, ann: char, highlight: char, opts: &Options<'_>) {
    if opts.annotations {
        return emit_annotation(row, ann, highlight, opts);
    }
    let role = Role::from_annotation(ann);
    let bg = code_bg(role);
    row.push(cell(if ann == '/' { '╲' } else { ' ' }, Some(annotation_fg(role)), bg));
}

/// One side's code column, `avail` cells wide.
///
/// `paints` is false when the container resolved to zero rows, in which case
/// the cells are just the group background with no foreground at all.
fn emit_code_slot(row: &mut Row, s: &Slot<'_>, avail: usize, paints: bool, opts: &Options<'_>) {
    if !paints {
        for _ in 0..avail {
            row.push(cell(' ', None, group_bg()));
        }
        return;
    }
    match s.code {
        // `Content.styled("╲" * width, hatch_style)` under a transparent
        // `LINE_STYLES["/"]`, so the group background shows through.
        None => {
            let fg = annotation_fg(Role::Hatch);
            let bg = group_bg();
            for _ in 0..avail {
                row.push(cell('╲', Some(fg), bg));
            }
        }
        Some(text) => code_cell(row, text, s.side, s.src, s.ann, opts, avail),
    }
}

/// `_compose_split`'s collection pass: one slot per row per side, padded to the
/// same length after every opcode.
fn split_slots<'x>(a: &'x [&'x str], b: &'x [&'x str], g: &Group) -> (Vec<Slot<'x>>, Vec<Slot<'x>>) {
    let mut sa: Vec<Slot<'x>> = Vec::new();
    let mut sb: Vec<Slot<'x>> = Vec::new();

    for o in &g.ops {
        let (tag, i1, i2, j1, j2) = op_tuple(o);
        if tag == "equal" {
            for (k, line) in a[i1..i2].iter().enumerate() {
                // Both halves get the SAME Content, taken from `lines_a`.
                sa.push(Slot { num: Some(i1 + k + 1), num_b: None, ann: ' ', code: Some(line), side: Side::A, src: i1 + k });
                sb.push(Slot { num: Some(j1 + k + 1), num_b: None, ann: ' ', code: Some(line), side: Side::A, src: i1 + k });
            }
            continue;
        }
        if tag == "delete" || tag == "replace" {
            for (k, line) in a[i1..i2].iter().enumerate() {
                sa.push(Slot { num: Some(i1 + k + 1), num_b: None, ann: '-', code: Some(line), side: Side::A, src: i1 + k });
            }
        }
        if tag == "insert" || tag == "replace" {
            for (k, line) in b[j1..j2].iter().enumerate() {
                sb.push(Slot { num: Some(j1 + k + 1), num_b: None, ann: '+', code: Some(line), side: Side::B, src: j1 + k });
            }
        }
        fill_slots(&mut sa, &mut sb);
    }
    (sa, sb)
}

fn split_group(a: &[&str], b: &[&str], g: &Group, opts: &Options<'_>) -> Vec<Row> {
    let (sa, sb) = split_slots(a, b, g);

    let w = number_width(sa.iter().chain(sb.iter()).map(|s| s.num), sa.is_empty());

    let ann_w = if opts.annotations { 3 } else { 1 };
    let remaining = (opts.width as i64 - 2 * (w + 2 + ann_w) as i64).max(0);
    // Both code columns are `width: 1fr`, so `_resolve.resolve_fraction_unit`
    // sets 1fr = remaining / 2 -- except that it returns a unit of exactly 1
    // when there is nothing left at all (`if not remaining_space: return 1`),
    // which is why the group overflows by two cells instead of vanishing.
    // `_get_box_model` then floors the share for the region width but passes
    // `int(share)` to `get_content_height`, whose first line is
    // `if not width: return 0`. At exactly one spare cell 1fr is 1/2, so both
    // containers come out zero rows tall and neither paints anything.
    let (code_w_a, code_w_b, code_paints) = if remaining == 0 {
        (1usize, 1usize, true)
    } else {
        let a = (remaining / 2) as usize;
        (a, remaining as usize - a, remaining != 1)
    };

    let mut rows = Vec::new();
    for k in 0..sa.len() {
        let mut row: Row = Vec::new();
        emit_numbers(&mut row, &sa[k], w);
        emit_annotation(&mut row, sa[k].ann, '-', opts);
        emit_code_slot(&mut row, &sa[k], code_w_a, code_paints, opts);
        emit_numbers(&mut row, &sb[k], w);
        emit_annotation(&mut row, sb[k].ann, '+', opts);
        emit_code_slot(&mut row, &sb[k], code_w_b, code_paints, opts);
        pad_cells(&mut row, opts.width, Some(TEXT), group_bg());
        // At `remaining == 0` the group is two cells wider than the terminal.
        // The compositor crops each widget to its own region, so nothing past
        // the right edge is ever written -- unlike a folded row, which can
        // overflow because its strip under-reports its length.
        truncate_cells(&mut row, opts.width);
        rows.push(row);
    }
    rows
}

/// The whole split view.
pub fn split(a: &[&str], b: &[&str], groups: &[Group], opts: &Options<'_>) -> Vec<Row> {
    let (add, rem) = crate::diff::pipeline::counts(groups);
    let mut head = title_rows(&opts.path, add, rem, opts.width);
    head.push(border_row(opts.width));
    let mut rows = columnize(&head, opts.width);
    for (i, g) in groups.iter().enumerate() {
        if i > 0 {
            rows.push(columns(&split_ellipsis_row(opts.width), opts.width));
        }
        // `split_wrap_group` composes two write runs and so returns columns.
        rows.extend(if opts.wrap {
            split_wrap_group(a, b, g, opts)
        } else {
            columnize(&split_group(a, b, g, opts), opts.width)
        });
    }
    rows
}

// ---- wrap -----------------------------------------------------------------
//
// With `wrap` on, the gutter stops being sibling `LineAnnotations` widgets and
// moves INSIDE the code visual: `FoldedLineContent` is handed a pre-rendered
// `annotate` Content per line plus a `continuation` for its second and later
// rows, folds the code to `width - annotate.cell_length`, and concatenates the
// two. That changes the layout solve -- there are no `auto` siblings left, so
// the code column gets the whole width in unified and a plain half in split.

/// Which compose path is drawing the gutter. It fixes how many number columns
/// there are, what a missing line number looks like, and how wide the
/// continuation's edge-styled `▎…` run is.
#[derive(Clone, Copy)]
enum Chrome {
    /// `_compose_unified{,_wrap}`: `▎{a:>W} ` + ` {b:>W} ` + the marker column.
    Unified { w: usize },
    /// `_compose_split{,_wrap}`: `▎{n:>W} ` (or the hatch) + the marker column.
    Split { w: usize, side: Side },
}

impl Chrome {
    /// Cells the gutter occupies. The same on every row of a group, which is
    /// what makes `fold_width` a constant.
    fn len(self, annotations: bool) -> usize {
        let ann_w = if annotations { 3 } else { 1 };
        match self {
            Chrome::Unified { w } => 2 * (w + 2) + ann_w,
            Chrome::Split { w, .. } => w + 2 + ann_w,
        }
    }

    /// Cells of the continuation's `▎…` run: `_make_continuations` is handed
    /// the number columns and appends the marker column itself.
    fn gutter(self) -> usize {
        match self {
            Chrome::Unified { w } => 2 * w + 4,
            Chrome::Split { w, .. } => w + 2,
        }
    }
}

/// Unified's marker column: `Content(" {ann} " | " ")` under LINE then
/// ANNOTATION styles, so the marker's own color wins over the line tint.
fn emit_marker(row: &mut Row, ann: char, opts: &Options<'_>) {
    let role = Role::from_annotation(ann);
    let bg = code_bg(role);
    let fg = annotation_fg(role);
    row.push(cell(' ', Some(fg), bg));
    if opts.annotations {
        row.push(cell(ann, Some(fg), bg));
        row.push(cell(' ', Some(fg), bg));
    }
}

/// The number and marker columns for one row.
fn emit_gutter(row: &mut Row, s: &Slot<'_>, ch: Chrome, opts: &Options<'_>) {
    let role = Role::from_annotation(s.ann);
    match ch {
        Chrome::Unified { w } => {
            let nfg = Some(number_fg(role));
            let nbg = number_bg(role);
            row.push(cell('▎', Some(edge_fg(role)), edge_bg(role)));
            push_str(row, &num_field(s.num, w), nfg, nbg, false);
            row.push(cell(' ', nfg, nbg));
            row.push(cell(' ', nfg, nbg));
            push_str(row, &num_field(s.num_b, w), nfg, nbg, false);
            row.push(cell(' ', nfg, nbg));
            emit_marker(row, s.ann, opts);
        }
        Chrome::Split { w, side } => {
            emit_numbers(row, s, w);
            emit_annotation_wrap(row, s.ann, side.highlight(), opts);
        }
    }
}

/// `_make_continuations`: the gutter a folded line's second and later rows get.
/// The whole `▎…` run wears the EDGE style here, not just cell 0 as on a first
/// row, and the marker column shows `↪`.
///
/// With annotations on, `↪` carries ANNOTATION_STYLES for `+` and `-`; an
/// unchanged line keeps LINE_STYLES and is dimmed instead. Both LINE and the
/// dim resolve to `$text` here and pyte has no dim, so they are one color.
fn emit_continuation(row: &mut Row, ann: char, ch: Chrome, opts: &Options<'_>) {
    let role = Role::from_annotation(ann);
    let fg = Some(edge_fg(role));
    let bg = edge_bg(role);
    row.push(cell('▎', fg, bg));
    for _ in 1..ch.gutter() {
        row.push(cell(' ', fg, bg));
    }
    let c_bg = code_bg(role);
    let m_fg = if opts.annotations && ann != ' ' {
        annotation_fg(role)
    } else {
        inherit(line_styles(role).fg, c_bg)
    };
    row.push(cell(' ', Some(m_fg), c_bg));
    if opts.annotations {
        row.push(cell('↪', Some(m_fg), c_bg));
        row.push(cell(' ', Some(m_fg), c_bg));
    }
}

/// `Content.styled("╲" * width, hatch_style)`, for a line this side does not
/// have. `width` is the WIDGET's, so the strip overflows the gutter and the
/// scroll container clips it -- the visible row is hatch all the way across.
fn emit_hatch(row: &mut Row, width: usize) {
    let fg = annotation_fg(Role::Hatch);
    let bg = group_bg();
    while row_width(row) < width {
        row.push(cell('╲', Some(fg), bg));
    }
}

/// `Content.fold`: hard-fold into pieces of at most `width` cells, with no word
/// breaking. Returns char ranges into `text`.
///
/// It slices by CODEPOINT count and then backs off until the piece fits, so a
/// piece can come out a cell short when backing off crosses a double-width
/// character. It also clamps to a minimum of 2 cells even though the caller's
/// `fold_width` can be 1 -- which is why the piece count and the caller's
/// `line_count` disagree and the caller pads with blanks.
fn fold(text: &[char], width: usize) -> Vec<(usize, usize)> {
    if text.is_empty() {
        return vec![(0, 0)];
    }
    let width = width.max(2) as i64;
    let mut out = Vec::new();
    let mut pos = 0usize;
    loop {
        let end = (pos + width as usize).min(text.len());
        if end == pos {
            break;
        }
        let mut size = cells(&text[pos..end]);
        if size < width {
            // The tail: everything that is left fits.
            out.push((pos, end));
            break;
        }
        if size == width {
            // An exact fit is a whole piece, and there may be more after it.
            out.push((pos, end));
            pos = end;
            continue;
        }
        // `extra_cells // 2` codepoints off the end first, then one at a time.
        let mut cut = end;
        let jump = ((size - width) / 2) as usize;
        if jump > 0 {
            size -= cells(&text[cut - jump..cut]);
            cut -= jump;
        }
        while size > width && cut > pos {
            size -= cell_width(text[cut - 1]) as i64;
            cut -= 1;
        }
        out.push((pos, cut));
        pos = cut;
    }
    out
}

/// One folded piece of code, plus the padding `pad_right` gives it.
///
/// Returns true when the strip came out wider than the widget while declaring
/// itself exactly as wide. The caller leaves such a row wide: the compositor
/// crops to the declared length, which is a lie, so every cell reaches the
/// terminal and what survives depends on what is painted over it.
fn emit_fold(
    row: &mut Row,
    piece: &[char],
    from: usize,
    s: &Slot<'_>,
    opts: &Options<'_>,
    code_width: usize,
    ann_len: usize,
) -> bool {
    let role = Role::from_annotation(s.ann);
    let c_bg = code_bg(role);
    let marks = marks_for(opts.inline, s.side, s.src);
    let syms = opts.syntax.side(s.side).get(s.src).map(Vec::as_slice).unwrap_or(&[]);
    let to = from + piece.len();
    let size = cells(piece);
    // `avail` is the piece's own width: emit it whole and pad below, because
    // Textual pads with `pad_right` (spans untouched) rather than by clipping.
    emit_code(
        row,
        piece,
        c_bg,
        marks.get(from..to).unwrap_or(&[]),
        syms.get(from..to).unwrap_or(&[]),
        inline_bg(s.side),
        size.max(0) as usize,
    );
    // `if line.cell_length < width: pad_right(width - cell_length - annotate)`.
    if size < code_width as i64 {
        let pad = code_width as i64 - size - ann_len as i64;
        for _ in 0..pad.max(0) {
            row.push(cell(' ', Some(TEXT), c_bg));
        }
        // A negative count is where `fold`'s 2-cell floor outruns a 1-cell
        // `fold_width`. `pad_right` appends `" " * -1` -- nothing -- but still
        // subtracts from the cached cell length, so the strip declares itself
        // exactly `code_width` while holding more.
        return pad < 0;
    }
    false
}

/// One gutter-and-code column, folded: `FoldedLineContent.render_strips`.
///
/// Each source line becomes `ceil(code_length / fold_width)` rows, the first
/// wearing the number gutter and the rest the continuation. `lengths` comes
/// from the caller rather than from this side's own text, so that the two
/// halves of a split group fold against a shared row count.
fn fold_column(
    slots: &[Slot<'_>],
    lengths: &[usize],
    code_width: usize,
    ch: Chrome,
    opts: &Options<'_>,
) -> Vec<Row> {
    let ann_len = ch.len(opts.annotations);
    let fold_width = (code_width as i64 - ann_len as i64).max(1) as usize;
    let mut rows = Vec::new();
    for (k, s) in slots.iter().enumerate() {
        let line_count = lengths[k].div_ceil(fold_width);
        let mut row = Row::new();
        match s.code {
            // A hatch filler repeats its gutter: `render_strips` appends
            // `annotate`, never `continuation`, for a `None` line.
            None => {
                for _ in 0..line_count {
                    row.clear();
                    emit_gutter(&mut row, s, ch, opts);
                    emit_hatch(&mut row, code_width);
                    truncate_cells(&mut row, code_width);
                    rows.push(row.clone());
                }
            }
            Some(text) => {
                let chars: Vec<char> = text.chars().collect();
                let folded = fold(&chars, fold_width);
                for r in 0..line_count.max(folded.len()) {
                    row.clear();
                    if r == 0 {
                        emit_gutter(&mut row, s, ch, opts);
                    } else {
                        emit_continuation(&mut row, s.ann, ch, opts);
                    }
                    let (from, to) = folded.get(r).copied().unwrap_or((chars.len(), chars.len()));
                    let to = to.min(chars.len());
                    let from = from.min(to);
                    let overflow =
                        emit_fold(&mut row, &chars[from..to], from, s, opts, code_width, ann_len);
                    if !overflow {
                        truncate_cells(&mut row, code_width);
                    }
                    rows.push(row.clone());
                }
            }
        }
    }
    rows
}

/// `_compose_unified_wrap`. The DiffCode is the group's only child, so it takes
/// the whole terminal width and the gutter comes out of it.
fn unified_wrap_group(a: &[&str], b: &[&str], g: &Group, opts: &Options<'_>) -> Vec<Row> {
    let slots = unified_slots(a, b, g);
    let w = number_width(
        slots.iter().map(|s| s.num).chain(slots.iter().map(|s| s.num_b)),
        slots.is_empty(),
    );
    let lengths: Vec<usize> = slots.iter().map(|s| s.cell_len()).collect();
    fold_column(&slots, &lengths, opts.width, Chrome::Unified { w }, opts)
}

/// The cells a split half shows below its last folded row: the scroll container
/// has no background of its own, so the `.diff-group` tint shows through with
/// no foreground at all.
fn blank_half(width: usize) -> Row {
    vec![cell(' ', None, group_bg()); width]
}

/// `_compose_split_wrap`. Both halves fold against `code_lengths` -- the max of
/// the two sides per row -- so a long line on one side keeps the other's hatch
/// rows aligned with it. They still come out different heights when the two
/// `1fr` columns differ by a cell, and the shorter half shows group background
/// below its last row.
fn split_wrap_group(a: &[&str], b: &[&str], g: &Group, opts: &Options<'_>) -> Vec<Row> {
    let (sa, sb) = split_slots(a, b, g);
    let w = number_width(sa.iter().chain(sb.iter()).map(|s| s.num), sa.is_empty());
    let lengths: Vec<usize> =
        sa.iter().zip(sb.iter()).map(|(x, y)| x.cell_len().max(y.cell_len())).collect();

    // No `auto` siblings this time, so `remaining` is the whole width and the
    // two `1fr` containers halve it, odd cell to the right.
    let left = opts.width / 2;
    let la = fold_column(&sa, &lengths, left, Chrome::Split { w, side: Side::A }, opts);
    let lb = fold_column(
        &sb,
        &lengths,
        opts.width - left,
        Chrome::Split { w, side: Side::B },
        opts,
    );

    let gap_a = blank_half(left);
    let gap_b = blank_half(opts.width - left);
    let mut rows = Vec::new();
    for k in 0..la.len().max(lb.len()) {
        // Two write runs, one per scroll container. A half wider than its widget
        // spills into the columns after it, and whatever is painted there next
        // wins -- the right half over the left half's spill, the screen edge over
        // the right half's.
        let mut out = blank_columns(opts.width);
        write_run(&mut out, la.get(k).unwrap_or(&gap_a), 0, opts.width);
        write_run(&mut out, lb.get(k).unwrap_or(&gap_b), left, opts.width);
        rows.push(out);
    }
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Offsets pinned against `rich._wrap.divide_line` by
    /// `py/dump_wrap_cases.py`: every width that actually breaks a line, over
    /// eleven titles covering the fold path, wide characters, and leading and
    /// trailing whitespace.
    #[test]
    fn divide_line_matches_rich() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let raw = std::fs::read_to_string(root.join("fixtures/wrap_cases.json")).expect("cases");
        let cases = serde_json::from_str::<serde_json::Value>(&raw).expect("json");
        let list = cases.as_array().expect("an array of cases");
        assert!(!list.is_empty(), "no cases");
        for case in list {
            let text = case["text"].as_str().expect("text");
            let width = case["width"].as_i64().expect("width");
            let want: Vec<usize> = case["offsets"]
                .as_array()
                .expect("offsets")
                .iter()
                .map(|v| v.as_u64().expect("an offset") as usize)
                .collect();
            let chars: Vec<char> = text.chars().collect();
            assert_eq!(divide_line(&chars, width, true), want, "divide_line({text:?}, {width})");
        }
    }

    /// Piece boundaries pinned against `Content.fold` by `py/dump_fold_cases.py`:
    /// every width that folds, the two-cell floor, and the exact-fit boundary,
    /// over lines covering wide characters, long words and trailing spaces. The
    /// tail branch (`< width`, stop) and the exact-fit branch (`== width`, keep
    /// going) are separate code paths and are easy to merge by accident.
    #[test]
    fn fold_matches_textual() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let raw = std::fs::read_to_string(root.join("fixtures/fold_cases.json")).expect("cases");
        let cases = serde_json::from_str::<serde_json::Value>(&raw).expect("json");
        let list = cases.as_array().expect("an array of cases");
        assert!(!list.is_empty(), "no cases");
        for case in list {
            let text = case["text"].as_str().expect("text");
            let width = case["width"].as_u64().expect("width") as usize;
            let want: Vec<(usize, usize)> = case["spans"]
                .as_array()
                .expect("spans")
                .iter()
                .map(|span| {
                    let pair = span.as_array().expect("a [from, to] pair");
                    let from = pair[0].as_u64().expect("from") as usize;
                    let to = pair[1].as_u64().expect("to") as usize;
                    (from, to)
                })
                .collect();
            let chars: Vec<char> = text.chars().collect();
            assert_eq!(fold(&chars, width), want, "fold({text:?}, {width})");
        }
    }

    /// The title breaks where rich says, `rstrip()`s every line but the last,
    /// and pads past the text with no foreground at all.
    #[test]
    fn title_wraps_rstrips_and_pads_unstyled() {
        let rows = title_rows("source.py", 1, 1, 12);
        let plain: Vec<String> = rows.iter().map(|r| r.iter().map(|c| c.ch).collect()).collect();
        assert_eq!(plain, ["📄 source.py", "(+1, -1)    "]);
        assert!(rows.iter().all(|r| row_width(r) == 12));
        assert!(rows[1][..8].iter().all(|c| c.fg.is_some()), "the text keeps its color");
        assert!(rows[1][8..].iter().all(|c| c.fg.is_none()), "the padding does not");
    }

    /// At exactly one spare cell both `1fr` code columns resolve to zero rows
    /// -- `_get_box_model` asks `get_content_height` for `int(1/2)` columns and
    /// that returns 0 -- so they paint nothing but the group background. One
    /// cell wider and 1fr is a whole cell again.
    #[test]
    fn split_collapses_the_code_columns_at_one_spare_cell() {
        let a = ["a = 1", "b = 2"];
        let b = ["a = 2", "b = 2"];
        let groups = crate::diff::pipeline::diff(&a, &b);
        let inline = crate::diff::pipeline::inline_marks(&a, &b, &groups);
        let syntax = Syntax::plain(a.len(), b.len());
        // W = 1, so the number and annotation columns take 2 * (3 + 1) = 8.
        let first_code_row = |width: usize| -> Row {
            let opts = Options::new(width, "source.py", &inline, &syntax);
            let rows = split(&a, &b, &groups, &opts);
            rows.into_iter()
                .find(|r| r.iter().filter(|c| c.ch == '▎').count() == 2)
                .unwrap_or_else(|| panic!("no two-number row at width {width}"))
        };
        let row = first_code_row(9);
        assert_eq!(row.len(), 9);
        assert_eq!(row[8].ch, ' ');
        assert_eq!(row[8].fg, None, "the collapsed column paints no foreground");
        assert_eq!(row[8].bg, group_bg());

        let row = first_code_row(10);
        assert_eq!(row.len(), 10);
        assert_eq!(row[4].ch, 'a', "code_a is one cell at width 10");
        assert!(row[4].fg.is_some() && row[9].fg.is_some(), "{row:?}");
    }

    /// Cropping a code column through a double-width character leaves a space
    /// wearing that character's own style: `Content.truncate` -> `set_cell_size`
    /// swaps the glyph but keeps the codepoint count, so `_trim_spans` still
    /// covers the cell. The row stays exactly `avail` cells wide.
    #[test]
    fn a_clipped_wide_character_leaves_a_styled_space() {
        let red = Sym {
            fg: Some(rgba(255, 0, 0, 1.0)),
            ..Sym::PLAIN
        };
        let syms = [Sym::PLAIN, red, red];
        let mut row = Row::new();
        let wide: Vec<char> = "a\u{4e16}\u{754c}".chars().collect();
        emit_code(
            &mut row,
            &wide,
            code_bg(Role::Added),
            &[],
            &syms,
            INLINE_ADDED_BG,
            2,
        );
        assert_eq!(row_width(&row), 2, "{row:?}");
        assert_eq!(row[0].ch, 'a');
        assert_eq!(row[1].ch, ' ', "the straddling glyph becomes a space");
        assert_eq!(row[1].fg, Some((255, 0, 0)), "and keeps its own color");
    }

    /// Where the second half starts, captured from textual-diff-view at each
    /// width: `remaining = width - 2 * ((W + 2) + ann_w)`, halved, with the odd
    /// cell going to the RIGHT code column.
    #[test]
    fn split_column_positions_match_the_capture() {
        let a = ["a = 1", "b = 2"];
        let b = ["a = 2", "b = 2"];
        let groups = crate::diff::pipeline::diff(&a, &b);
        let inline = crate::diff::pipeline::inline_marks(&a, &b, &groups);
        let syntax = Syntax::plain(a.len(), b.len());
        // (width, second "▎" x). At width 8 the number columns alone fill the
        // terminal, both code containers fall back to their minimal 1 cell and
        // the group overflows -- so the second half starts at 4 + 1 = 5.
        for (width, want) in [
            (8usize, 5usize),
            (30, 15),
            (41, 20),
            (80, 40),
            (99, 49),
            (100, 50),
            (101, 50),
            (103, 51),
        ] {
            let opts = Options::new(width, "source.py", &inline, &syntax);
            let rows = split(&a, &b, &groups, &opts);
            let edges: Vec<Vec<usize>> = rows
                .iter()
                .map(|r| r.iter().enumerate().filter(|(_, c)| c.ch == '▎').map(|(i, _)| i).collect())
                .collect();
            let xs = edges
                .iter()
                .find(|xs| xs.len() == 2)
                .unwrap_or_else(|| panic!("no two-number row at width {width}"));
            assert_eq!((xs[0], xs[1]), (0, want), "width {width}");
        }
    }
}

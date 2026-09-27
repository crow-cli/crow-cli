//! Resolved colors for the shades-of-purple theme, and Textual's blending.
//!
//! Nothing here is derived from first principles: every value was read out of
//! a live Textual `DiffView` (`py/probe_styles.py` dumps the four style maps,
//! `show_diff.py --dump-theme` dumps the 168 resolved theme variables) and the
//! blend rule was checked against a PTY capture cell by cell.
//!
//! Textual composites each layer as `a*fg + (1-a)*bg` and FLOORS the result --
//! `rgba(51,195,0,.09)` over `#35335b` gives `#343f52`, whose green channel is
//! 63.99 -> 0x3f, not 0x40.

/// A color with alpha, as Textual's style maps carry them.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rgba {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: f32,
}

pub type Rgb = (u8, u8, u8);

pub const fn rgba(r: u8, g: u8, b: u8, a: f32) -> Rgba {
    Rgba { r, g, b, a }
}

pub const TRANSPARENT: Rgba = rgba(0, 0, 0, 0.0);

/// Composite `fg` over an opaque `bg`, flooring each channel like Textual.
pub fn blend(fg: Rgba, bg: Rgb) -> Rgb {
    if fg.a <= 0.0 {
        return bg;
    }
    if fg.a >= 1.0 {
        return (fg.r, fg.g, fg.b);
    }
    let inv = 1.0 - fg.a;
    (
        (fg.a * fg.r as f32 + inv * bg.0 as f32).floor() as u8,
        (fg.a * fg.g as f32 + inv * bg.1 as f32).floor() as u8,
        (fg.a * fg.b as f32 + inv * bg.2 as f32).floor() as u8,
    )
}

/// Fold a stack of layers over a base, innermost last.
pub fn stack(layers: &[Rgba], base: Rgb) -> Rgb {
    layers.iter().fold(base, |acc, l| blend(*l, acc))
}

// ---- shades-of-purple, as Textual resolves it -----------------------------
// themes.py declares accent #FF2C70 / success #3AD900 / warning #FF9D00 /
// error #EC3A37; Textual normalizes each by one step, so these are the values
// that actually reach the terminal.
pub const APP_BG: Rgb = (0x2D, 0x2B, 0x55);
pub const TEXT: Rgb = (0xFF, 0xFF, 0xFF);
pub const TEXT_DIM: Rgb = (0xB7, 0xB6, 0xC5);
pub const TEXT_SUCCESS: Rgb = (0x7C, 0xE5, 0x56);
pub const TEXT_ERROR: Rgb = (0xF2, 0x7C, 0x7B);
pub const TEXT_PRIMARY: Rgb = (0xD3, 0xB7, 0xFB);
pub const TEXT_SECONDARY: Rgb = (0xCC, 0x97, 0xFF);
pub const TEXT_ACCENT: Rgb = (0xFF, 0x73, 0xA0);
pub const TEXT_WARNING: Rgb = (0xFF, 0xBE, 0x56);

/// `.diff-group { background: $foreground 4% }`
pub const GROUP_BG: Rgba = rgba(255, 255, 255, 0.04);

/// The inline character-level highlight.
///
/// These two are fetched with `get_visual_style(cc)` and NO `partial=True`,
/// unlike the four style maps -- so they come back already composited over the
/// whole ancestor chain as opaque colors. They therefore *replace* the line
/// tint on the cells they cover rather than blending into it.
pub const INLINE_ADDED_BG: Rgb = (48, 95, 59); // #305f3b, $success 30% over $background
pub const INLINE_REMOVED_BG: Rgb = (102, 47, 76); // #662f4c, $error 30% over $background

/// `.title { border-bottom: dashed $foreground 20% }`
pub const TITLE_BORDER: Rgba = rgba(255, 255, 255, 0.20);

/// The group background as a concrete color.
pub fn group_bg() -> Rgb {
    blend(GROUP_BG, APP_BG)
}

// ---- the four style maps, keyed by role ----------------------------------

/// What a line is: unchanged, added, removed, or the folded/hatch filler.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Equal,
    Added,
    Removed,
    Hatch,
}

impl Role {
    pub fn from_annotation(a: char) -> Role {
        match a {
            '+' => Role::Added,
            '-' => Role::Removed,
            '/' => Role::Hatch,
            _ => Role::Equal,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct RoleStyle {
    pub fg: Rgba,
    pub bg: Rgba,
}

const fn rs(fg: Rgba, bg: Rgba) -> RoleStyle {
    RoleStyle { fg, bg }
}

// number_styles: the two line-number columns.
const NUMBER: [RoleStyle; 4] = [
    rs(rgba(255, 255, 255, 0.30), rgba(247, 247, 247, 0.0291)), // Equal
    rs(rgba(124, 229, 86, 0.80), rgba(45, 173, 0, 0.16)),       // Added
    rs(rgba(242, 124, 123, 0.80), rgba(188, 46, 44, 0.16)),     // Removed
    rs(rgba(255, 255, 255, 0.30), rgba(247, 247, 247, 0.0291)), // Hatch (unused)
];

// edge_styles: the one-cell "▎" column.
const EDGE: [RoleStyle; 4] = [
    rs(rgba(255, 255, 255, 0.10), rgba(247, 247, 247, 0.0291)),
    rs(rgba(124, 229, 86, 0.30), rgba(45, 173, 0, 0.16)),
    rs(rgba(242, 124, 123, 0.30), rgba(188, 46, 44, 0.16)),
    rs(rgba(255, 255, 255, 0.10), rgba(247, 247, 247, 0.0291)),
];

// line_styles: the code area's background tint.
const LINE: [RoleStyle; 4] = [
    rs(TRANSPARENT, TRANSPARENT),
    rs(TRANSPARENT, rgba(51, 195, 0, 0.09)),
    rs(TRANSPARENT, rgba(211, 52, 49, 0.09)),
    rs(TRANSPARENT, TRANSPARENT),
];

// annotation_styles: the narrow column between the numbers and the code.
const ANNOTATION: [RoleStyle; 4] = [
    rs(rgba(255, 255, 255, 0.00), TRANSPARENT),
    rs(rgba(124, 229, 86, 0.95), TRANSPARENT),
    rs(rgba(242, 124, 123, 0.95), TRANSPARENT),
    rs(rgba(255, 255, 255, 0.15), TRANSPARENT),
];

fn idx(r: Role) -> usize {
    match r {
        Role::Equal => 0,
        Role::Added => 1,
        Role::Removed => 2,
        Role::Hatch => 3,
    }
}

pub fn number_styles(r: Role) -> RoleStyle {
    NUMBER[idx(r)]
}
pub fn edge_styles(r: Role) -> RoleStyle {
    EDGE[idx(r)]
}
pub fn line_styles(r: Role) -> RoleStyle {
    LINE[idx(r)]
}
pub fn annotation_styles(r: Role) -> RoleStyle {
    ANNOTATION[idx(r)]
}

/// Background of the "▎" cell for a role.
pub fn edge_bg(r: Role) -> Rgb {
    stack(&[GROUP_BG, edge_styles(r).bg], APP_BG)
}

/// Background of a line-number cell for a role.
pub fn number_bg(r: Role) -> Rgb {
    stack(&[GROUP_BG, number_styles(r).bg], APP_BG)
}

/// Background of the annotation column and of the code, for a role.
pub fn code_bg(r: Role) -> Rgb {
    stack(&[GROUP_BG, line_styles(r).bg], APP_BG)
}

/// Resolve a foreground over `bg`.
///
/// Alpha zero is not "blend to invisible": CSS `color: transparent` leaves the
/// foreground unset, so Textual falls back to `$text`. `annotation_styles` for
/// an unchanged line is exactly that, and it renders `#ffffff`, not the bg.
pub fn inherit(fg: Rgba, bg: Rgb) -> Rgb {
    if fg.a <= 0.0 {
        TEXT
    } else {
        blend(fg, bg)
    }
}

/// Textual's `Color.brightness` -- ITU-R BT.601 luma, not the sRGB one.
pub fn brightness(c: Rgb) -> f32 {
    0.299 * c.0 as f32 / 255.0 + 0.587 * c.1 as f32 / 255.0 + 0.114 * c.2 as f32 / 255.0
}

/// Resolve an `auto` foreground (`$text`) against a background.
///
/// `Color.__add__` does `bg.blend(bg.get_contrast_text(a), a, 1.0)`, and
/// `get_contrast_text` picks white below 0.5 luma and black above. Every
/// background this view produces is dark -- the lightest is the inline-added
/// `#305f3b` at 0.301 -- so it is always white, but the test is cheap.
pub fn auto_text(bg: Rgb) -> Rgb {
    let target = if brightness(bg) < 0.5 { TEXT } else { (0, 0, 0) };
    blend(rgba(target.0, target.1, target.2, 1.0), bg)
}

/// Foreground of the "▎" glyph, over its own background.
pub fn edge_fg(r: Role) -> Rgb {
    inherit(edge_styles(r).fg, edge_bg(r))
}

/// Foreground of a line number, over its own background.
pub fn number_fg(r: Role) -> Rgb {
    inherit(number_styles(r).fg, number_bg(r))
}

/// Foreground of the annotation column, over the code background.
pub fn annotation_fg(r: Role) -> Rgb {
    inherit(annotation_styles(r).fg, code_bg(r))
}

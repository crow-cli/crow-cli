//! The crow-cli lockup as terminal art.
//!
//! `crow` carries the brand gradient (pale → brand in dark mode, brand →
//! pale in light); `-cli` runs its own ramp in the theme's `ok` hue — mint in
//! every builtin pack, the complement of the pink-and-blue `crow` — so the two
//! words read as two hues rather than one flat ink. Wide terminals get the
//! full wordmark; narrower ones degrade to plain bold text.

use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

use crate::theme::{lerp, Mode, Theme, DEEPSEEK_200, DEEPSEEK_50};

/// The crow-cli wordmark, 6 rows of [`ART_WIDTH`] columns.
pub const CROW_CLI: [&str; 6] = [
	r#"                                                   __    "#,
	r#"  ___   _ __   ___   __  __  __              __   /\_\   "#,
	r#" /'___\/\`'__\/ __`\/\ \/\ \/\ \  _______  /'__`\ \/\ \  "#,
	r#"/\ \__/\ \ \//\ \L\ \ \ \_/ \_/ \/\______\/\ \L\.\_\ \ \ "#,
	r#"\ \____\\ \_\\ \____/\ \___x___/'\/______/\ \__/.\_\\ \_\"#,
	r#" \/____/ \/_/ \/___/  \/__//__/            \/__/\/_/ \/_/"#,
];

/// Columns per row of [`CROW_CLI`]. Rows stay rectangular so centering
/// cannot shear the wordmark.
const ART_WIDTH: usize = 57;

/// The column `crow` ends on: everything before it takes the gradient,
/// `-cli` from here on takes the terminal ink. The hyphen box top lives in
/// row 2 at columns 34-40, so the split hands the whole box to `-cli`.
const ART_SPLIT: usize = 34;

/// The wordmark as plain text, for terminals too narrow for the art.
const WORDMARK: &str = "crow-cli";

fn split_row(row: &str, at: usize) -> (String, String) {
    let mut chars = row.chars();
    let crow = chars.by_ref().take(at).collect();
    let cli = chars.collect();
    (crow, cli)
}

/// A pale tint of `c`, for the far end of a ramp.
fn pale(c: Color) -> Color {
    lerp(c, Color::Rgb(255, 255, 255), 0.55)
}

fn split_logo_lines(
    rows: &[&str],
    split: usize,
    art_width: usize,
    theme: &Theme,
    width: u16,
) -> Vec<Line<'static>> {
    let pad = (width as usize).saturating_sub(art_width) / 2;
    let (ocean_top, ocean_bottom) = match theme.mode {
        Mode::Dark => (DEEPSEEK_50, theme.brand),
        Mode::Light => (theme.brand, DEEPSEEK_200),
    };
    let (mint_top, mint_bottom) = match theme.mode {
        Mode::Dark => (pale(theme.ok), theme.ok),
        Mode::Light => (theme.ok, pale(theme.ok)),
    };
    let last = rows.len().saturating_sub(1).max(1);
    rows.iter()
        .enumerate()
        .map(|(row_index, row)| {
            let t = row_index as f32 / last as f32;
            let (crow, cli) = split_row(row, split);
            Line::from(vec![
                Span::raw(" ".repeat(pad)),
                Span::styled(crow, Style::default().fg(lerp(ocean_top, ocean_bottom, t))),
                Span::styled(cli, Style::default().fg(lerp(mint_top, mint_bottom, t))),
            ])
        })
        .collect()
}

/// The crow-cli logo rows, split into a gradient `crow` and a gradient
/// `-cli`, centered to `width`. Terminals too narrow for the wordmark get the
/// same two hues as plain bold text.
pub fn crow_cli_logo_lines(theme: &Theme, width: u16) -> Vec<Line<'static>> {
    if width < ART_WIDTH as u16 + 2 {
        if width >= WORDMARK.len() as u16 {
            let pad = (width as usize).saturating_sub(WORDMARK.len()) / 2;
            return vec![Line::from(vec![
                Span::raw(" ".repeat(pad)),
                Span::styled(
                    "crow".to_string(),
                    Style::default()
                        .fg(theme.brand)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    "-cli".to_string(),
                    Style::default().fg(theme.ok).add_modifier(Modifier::BOLD),
                ),
            ])];
        }
        return Vec::new();
    }
    split_logo_lines(&CROW_CLI, ART_SPLIT, ART_WIDTH, theme, width)
}

#[cfg(test)]
#[path = "../tests/unit/logo__tests.rs"]
mod tests;

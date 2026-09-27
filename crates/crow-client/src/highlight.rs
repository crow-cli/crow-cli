//! Syntax highlighting for fenced code: syntect's tokenizer, crow's palette.
//!
//! tui-markdown ships its own `highlight-code` feature, but `markdown::render`
//! re-renders code rows itself — it has to, to wrap them to the chat width and
//! paint the panel background — so the token colors are produced here and
//! handed to that pass as styled runs.
//!
//! The palette obeys the same rule the rest of markdown does: grayscale body,
//! brand-blue accents, red reserved for errors. Code gets five roles on top of
//! the default foreground — comments (muted italic), strings (green),
//! constants (amber), keywords (brand blue) and names (slate) — all of them
//! mode-aware theme tokens, so a light skin recolors them the way it recolors
//! everything else.

use std::sync::OnceLock;

use ratatui::style::{Color as TuiColor, Modifier, Style};
use syntect::easy::HighlightLines;
use syntect::highlighting::{
    Color as SynColor, FontStyle, StyleModifier, Theme as SynTheme, ThemeItem, ThemeSettings,
};
use syntect::parsing::{SyntaxReference, SyntaxSet};

use crate::theme::Theme;

/// The embedded syntax dump, unpacked once per process.
fn syntaxes() -> &'static SyntaxSet {
    static SET: OnceLock<SyntaxSet> = OnceLock::new();
    SET.get_or_init(SyntaxSet::load_defaults_newlines)
}

/// Fence labels the default set spells differently, or does not ship at all.
/// A label with no entry and no grammar renders framed but uncolored.
const SYNTAX_ALIASES: [(&str, &str); 3] = [
    ("typescript", "javascript"),
    ("tsx", "javascript"),
    ("console", "bash"),
];

/// The grammar behind a fence label, if the default set has one.
pub fn syntax_for(lang: &str) -> Option<&'static SyntaxReference> {
    let label = lang.trim().to_ascii_lowercase();
    let token = SYNTAX_ALIASES
        .iter()
        .find(|(alias, _)| *alias == label)
        .map_or(label.as_str(), |(_, token)| *token);
    syntaxes().find_syntax_by_token(token)
}

/// Styled runs for each line of one fenced code block, aligned with
/// `code.lines()`. A language syntect has no grammar for falls back to the
/// plain code style rather than to nothing.
pub fn code_block(code: &str, lang: &str, theme: &Theme) -> Vec<Vec<(String, Style)>> {
    let base = Style::default().fg(theme.fg).bg(theme.panel);
    let Some(syntax) = syntax_for(lang) else {
        return code
            .lines()
            .map(|line| vec![(line.to_owned(), base)])
            .collect();
    };
    let palette = palette(theme, base);
    let mut highlighter = HighlightLines::new(syntax, &palette);
    code.lines()
        .map(|line| {
            // The default dump is the "newlines" build: it wants the line
            // ending kept, and hands it back inside the last run.
            let mut with_ending = line.to_owned();
            with_ending.push('\n');
            match highlighter.highlight_line(&with_ending, syntaxes()) {
                Ok(ranges) => {
                    let mut runs: Vec<(String, Style)> = Vec::new();
                    for (token, text) in ranges {
                        let text = text.trim_end_matches(['\n', '\r']);
                        if text.is_empty() {
                            continue;
                        }
                        runs.push((text.to_owned(), token_style(base, &token)));
                    }
                    if runs.is_empty() {
                        runs.push((String::new(), base));
                    }
                    runs
                }
                // A line the grammar chokes on still has to render.
                Err(_) => vec![(line.to_owned(), base)],
            }
        })
        .collect()
}

/// One token run's style: the syntect foreground and font flags layered over
/// the panel background every code row shares.
fn token_style(base: Style, token: &syntect::highlighting::Style) -> Style {
    let mut style = base.fg(TuiColor::Rgb(
        token.foreground.r,
        token.foreground.g,
        token.foreground.b,
    ));
    if token.font_style.contains(FontStyle::ITALIC) {
        style = style.add_modifier(Modifier::ITALIC);
    }
    if token.font_style.contains(FontStyle::BOLD) {
        style = style.add_modifier(Modifier::BOLD);
    }
    if token.font_style.contains(FontStyle::UNDERLINE) {
        style = style.add_modifier(Modifier::UNDERLINED);
    }
    style
}

/// The syntect theme, built from the live palette so a skin change recolors
/// code the same frame it recolors everything else.
fn palette(theme: &Theme, base: Style) -> SynTheme {
    let syn = |color: TuiColor| -> SynColor {
        match color {
            TuiColor::Rgb(r, g, b) => SynColor { r, g, b, a: 255 },
            _ => SynColor {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            },
        }
    };
    let role = |scope: &str, fg: TuiColor, italic: bool| ThemeItem {
        scope: scope.parse().expect("scope selector parses"),
        style: StyleModifier {
            foreground: Some(syn(fg)),
            background: None,
            font_style: Some(if italic {
                FontStyle::ITALIC
            } else {
                FontStyle::empty()
            }),
        },
    };
    SynTheme {
        name: Some("crow".into()),
        author: Some("crow".into()),
        settings: ThemeSettings {
            foreground: base.fg.map(syn),
            background: base.bg.map(syn),
            ..ThemeSettings::default()
        },
        scopes: vec![
            role("comment", theme.caption, true),
            role("string", theme.ok, false),
            role("constant.numeric", theme.warn, false),
            role("constant.language", theme.warn, false),
            role("constant.character.escape", theme.warn, false),
            // Operators stay the default gray: only the words are keywords.
            role("keyword - keyword.operator", theme.brand_soft, false),
            role("storage", theme.brand_soft, false),
            role("support.function.builtin", theme.brand_soft, false),
            role("entity.name.function", theme.hint, false),
            role("entity.name.type", theme.hint, false),
            role("support.type", theme.hint, false),
            role("variable.parameter", theme.fg_secondary, false),
            role("punctuation", theme.fg_secondary, false),
        ],
    }
}

#[cfg(test)]
#[path = "../tests/unit/highlight__tests.rs"]
mod tests;

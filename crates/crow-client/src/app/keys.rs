//! keys: extracted verbatim from src/app.rs (Phase 1 split).

use std::time::{Duration, Instant};
use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers};

#[derive(Clone, Copy)]
pub(crate) struct CtrlCQuitChord {
    pub(crate) started: Instant,
    pub(crate) presses: u8,
    pub(crate) required: u8,
}
pub(crate) const TIP_TTL: Duration = Duration::from_secs(4);
/// How long the `↥` jump flash keeps the jumped user prompt background-
/// washed before it restores to normal (issue #103).
pub const PROMPT_FLASH_TTL: Duration = Duration::from_secs(5);
/// How often the composer cap re-checks the workspace git branch (tick
/// cadence). Catches checkouts done by the agent or in another terminal;
/// `!git checkout` in the session shell refreshes immediately instead.
pub(crate) const GIT_CHECK_INTERVAL: Duration = Duration::from_secs(5);

/// Some terminal layers incorrectly wrap Kitty/CSI-u key reports in
/// bracketed-paste markers. Crossterm then exposes the key bytes as a paste,
/// so recover them only when the *entire* payload is made of CSI-u keys.
pub(crate) fn decode_leaked_csi_u_keys(text: &str) -> Option<Vec<KeyEvent>> {
    if text.is_empty() {
        return None;
    }

    let mut rest = text;
    let mut keys = Vec::new();
    while !rest.is_empty() {
        let encoded = rest.strip_prefix("\u{1b}[")?;
        let end = encoded.find('u')?;
        keys.push(decode_csi_u_key(&encoded[..end])?);
        rest = &encoded[end + 1..];
    }
    Some(keys)
}

pub(crate) fn decode_csi_u_key(params: &str) -> Option<KeyEvent> {
    let mut fields = params.split(';');
    let codepoint = fields.next()?.split(':').next()?.parse::<u32>().ok()?;
    let modifier_and_kind = fields.next();
    // Text-as-codepoints and any other trailing fields are deliberately not
    // recovered: falling back to ordinary paste is safer than guessing.
    if fields.next().is_some() {
        return None;
    }

    let (modifier_mask, kind) = match modifier_and_kind {
        Some(field) => {
            let mut parts = field.split(':');
            let mask = parts.next()?.parse::<u32>().ok()?;
            if mask == 0 {
                return None;
            }
            let kind = match parts.next() {
                None | Some("1") => KeyEventKind::Press,
                Some("2") => KeyEventKind::Repeat,
                Some("3") => KeyEventKind::Release,
                Some(_) => return None,
            };
            if parts.next().is_some() {
                return None;
            }
            (mask - 1, kind)
        }
        None => (0, KeyEventKind::Press),
    };

    let mut modifiers = KeyModifiers::NONE;
    if modifier_mask & 1 != 0 {
        modifiers |= KeyModifiers::SHIFT;
    }
    if modifier_mask & 2 != 0 {
        modifiers |= KeyModifiers::ALT;
    }
    if modifier_mask & 4 != 0 {
        modifiers |= KeyModifiers::CONTROL;
    }
    if modifier_mask & 8 != 0 {
        modifiers |= KeyModifiers::SUPER;
    }
    if modifier_mask & 16 != 0 {
        modifiers |= KeyModifiers::HYPER;
    }
    if modifier_mask & 32 != 0 {
        modifiers |= KeyModifiers::META;
    }

    let ch = char::from_u32(codepoint)?;
    let code = match ch {
        '\u{1b}' => KeyCode::Esc,
        '\r' => KeyCode::Enter,
        '\t' if modifiers.contains(KeyModifiers::SHIFT) => KeyCode::BackTab,
        '\t' => KeyCode::Tab,
        '\u{7f}' => KeyCode::Backspace,
        _ => KeyCode::Char(ch),
    };
    Some(KeyEvent::new_with_kind(code, modifiers, kind))
}

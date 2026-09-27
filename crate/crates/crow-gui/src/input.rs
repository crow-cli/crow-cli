//! winit -> terminal-event translation.
//!
//! The runner speaks winit; applications speak [`crate::event`]. Everything
//! that bridges the two lives here, and none of it touches a window, a surface
//! or the platform: these are pure functions over winit's event payloads, so
//! they are unit-testable on the host and identical in the browser.
//!
//! Lifted from fresh-gui (`crates/fresh-gui/src/lib.rs:663-974`) — the
//! blueprint for this crate — with crossterm's types swapped for the service's
//! own [`crate::event`] shapes.

use winit::event::MouseButton as WinitMouseButton;
use winit::keyboard::{Key, KeyLocation, NamedKey};

use crate::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers, MediaKeyCode, ModifierKeyCode,
    MouseButton,
};

/// Convert winit modifier state to the service's [`KeyModifiers`].
pub fn translate_modifiers(mods: &winit::keyboard::ModifiersState) -> KeyModifiers {
    let mut result = KeyModifiers::NONE;
    if mods.shift_key() {
        result |= KeyModifiers::SHIFT;
    }
    if mods.control_key() {
        result |= KeyModifiers::CONTROL;
    }
    if mods.alt_key() {
        result |= KeyModifiers::ALT;
    }
    if mods.super_key() {
        result |= KeyModifiers::SUPER;
    }
    result
}

/// Translate a winit key event to the service's [`KeyEvent`].
///
/// `alt_location` tracks which Alt/Option key is held, used on macOS to
/// distinguish Left Alt (international character composition) from Right Alt
/// (keyboard shortcut modifier).
pub fn translate_key_event(
    event: &winit::event::KeyEvent,
    modifiers: KeyModifiers,
    alt_location: Option<KeyLocation>,
) -> Option<KeyEvent> {
    let (effective_modifiers, alt_override_char) =
        if cfg!(target_os = "macos") && modifiers.contains(KeyModifiers::ALT) {
            match alt_location {
                Some(KeyLocation::Left) => {
                    // Left Alt: strip ALT so the composed character is treated
                    // as plain text input rather than a shortcut.
                    (modifiers & !KeyModifiers::ALT, None)
                }
                Some(KeyLocation::Right) => {
                    // Right Alt: keep ALT for shortcuts, but undo the macOS
                    // Option-composition by deriving the base character from
                    // the physical key.
                    let base = physical_key_to_base_char(
                        &event.physical_key,
                        modifiers.contains(KeyModifiers::SHIFT),
                    );
                    (modifiers, base)
                }
                _ => (modifiers, None),
            }
        } else {
            (modifiers, None)
        };

    let code = match &event.logical_key {
        Key::Named(named) => translate_named_key(named, &event.location, effective_modifiers)?,
        Key::Character(ch) => {
            let c = alt_override_char.unwrap_or_else(|| ch.chars().next().unwrap_or('\0'));
            if c == '\0' {
                return None;
            }
            if c == '\t' && effective_modifiers.contains(KeyModifiers::SHIFT) {
                KeyCode::BackTab
            } else {
                KeyCode::Char(c)
            }
        }
        Key::Dead(_) | Key::Unidentified(_) => return None,
    };

    Some(KeyEvent {
        code,
        modifiers: effective_modifiers,
        kind: KeyEventKind::Press,
        state: KeyEventState::NONE,
    })
}

/// Map a winit physical key to its base US-layout character.
///
/// Used on macOS to undo the Option-key composition for Right Alt shortcuts.
fn physical_key_to_base_char(key: &winit::keyboard::PhysicalKey, shift: bool) -> Option<char> {
    use winit::keyboard::KeyCode as WK;
    use winit::keyboard::PhysicalKey;

    let PhysicalKey::Code(code) = key else {
        return None;
    };

    let base = match code {
        WK::KeyA => 'a',
        WK::KeyB => 'b',
        WK::KeyC => 'c',
        WK::KeyD => 'd',
        WK::KeyE => 'e',
        WK::KeyF => 'f',
        WK::KeyG => 'g',
        WK::KeyH => 'h',
        WK::KeyI => 'i',
        WK::KeyJ => 'j',
        WK::KeyK => 'k',
        WK::KeyL => 'l',
        WK::KeyM => 'm',
        WK::KeyN => 'n',
        WK::KeyO => 'o',
        WK::KeyP => 'p',
        WK::KeyQ => 'q',
        WK::KeyR => 'r',
        WK::KeyS => 's',
        WK::KeyT => 't',
        WK::KeyU => 'u',
        WK::KeyV => 'v',
        WK::KeyW => 'w',
        WK::KeyX => 'x',
        WK::KeyY => 'y',
        WK::KeyZ => 'z',
        WK::Digit0 => '0',
        WK::Digit1 => '1',
        WK::Digit2 => '2',
        WK::Digit3 => '3',
        WK::Digit4 => '4',
        WK::Digit5 => '5',
        WK::Digit6 => '6',
        WK::Digit7 => '7',
        WK::Digit8 => '8',
        WK::Digit9 => '9',
        WK::Minus => '-',
        WK::Equal => '=',
        WK::BracketLeft => '[',
        WK::BracketRight => ']',
        WK::Backslash => '\\',
        WK::Semicolon => ';',
        WK::Quote => '\'',
        WK::Comma => ',',
        WK::Period => '.',
        WK::Slash => '/',
        WK::Backquote => '`',
        _ => return None,
    };

    if shift && base.is_ascii_alphabetic() {
        Some(base.to_ascii_uppercase())
    } else {
        Some(base)
    }
}

/// Translate a winit [`NamedKey`] to the service's [`KeyCode`].
pub fn translate_named_key(
    key: &NamedKey,
    location: &winit::keyboard::KeyLocation,
    modifiers: KeyModifiers,
) -> Option<KeyCode> {
    use winit::keyboard::KeyLocation;

    Some(match key {
        // Navigation
        NamedKey::ArrowUp => KeyCode::Up,
        NamedKey::ArrowDown => KeyCode::Down,
        NamedKey::ArrowLeft => KeyCode::Left,
        NamedKey::ArrowRight => KeyCode::Right,
        NamedKey::Home => KeyCode::Home,
        NamedKey::End => KeyCode::End,
        NamedKey::PageUp => KeyCode::PageUp,
        NamedKey::PageDown => KeyCode::PageDown,

        // Editing
        NamedKey::Backspace => KeyCode::Backspace,
        NamedKey::Delete => KeyCode::Delete,
        NamedKey::Insert => KeyCode::Insert,
        NamedKey::Enter => KeyCode::Enter,
        NamedKey::Tab => {
            if modifiers.contains(KeyModifiers::SHIFT) {
                KeyCode::BackTab
            } else {
                KeyCode::Tab
            }
        }
        NamedKey::Space => KeyCode::Char(' '),
        NamedKey::Escape => KeyCode::Esc,

        // Function keys
        NamedKey::F1 => KeyCode::F(1),
        NamedKey::F2 => KeyCode::F(2),
        NamedKey::F3 => KeyCode::F(3),
        NamedKey::F4 => KeyCode::F(4),
        NamedKey::F5 => KeyCode::F(5),
        NamedKey::F6 => KeyCode::F(6),
        NamedKey::F7 => KeyCode::F(7),
        NamedKey::F8 => KeyCode::F(8),
        NamedKey::F9 => KeyCode::F(9),
        NamedKey::F10 => KeyCode::F(10),
        NamedKey::F11 => KeyCode::F(11),
        NamedKey::F12 => KeyCode::F(12),
        NamedKey::F13 => KeyCode::F(13),
        NamedKey::F14 => KeyCode::F(14),
        NamedKey::F15 => KeyCode::F(15),
        NamedKey::F16 => KeyCode::F(16),
        NamedKey::F17 => KeyCode::F(17),
        NamedKey::F18 => KeyCode::F(18),
        NamedKey::F19 => KeyCode::F(19),
        NamedKey::F20 => KeyCode::F(20),
        NamedKey::F21 => KeyCode::F(21),
        NamedKey::F22 => KeyCode::F(22),
        NamedKey::F23 => KeyCode::F(23),
        NamedKey::F24 => KeyCode::F(24),
        NamedKey::F25 => KeyCode::F(25),
        NamedKey::F26 => KeyCode::F(26),
        NamedKey::F27 => KeyCode::F(27),
        NamedKey::F28 => KeyCode::F(28),
        NamedKey::F29 => KeyCode::F(29),
        NamedKey::F30 => KeyCode::F(30),
        NamedKey::F31 => KeyCode::F(31),
        NamedKey::F32 => KeyCode::F(32),
        NamedKey::F33 => KeyCode::F(33),
        NamedKey::F34 => KeyCode::F(34),
        NamedKey::F35 => KeyCode::F(35),

        // Lock keys
        NamedKey::CapsLock => KeyCode::CapsLock,
        NamedKey::NumLock => KeyCode::NumLock,
        NamedKey::ScrollLock => KeyCode::ScrollLock,

        // Misc
        NamedKey::PrintScreen => KeyCode::PrintScreen,
        NamedKey::Pause => KeyCode::Pause,
        NamedKey::ContextMenu => KeyCode::Menu,

        // Media keys
        NamedKey::MediaPlay => KeyCode::Media(MediaKeyCode::Play),
        NamedKey::MediaPause => KeyCode::Media(MediaKeyCode::Pause),
        NamedKey::MediaPlayPause => KeyCode::Media(MediaKeyCode::PlayPause),
        NamedKey::MediaStop => KeyCode::Media(MediaKeyCode::Stop),
        NamedKey::MediaTrackNext => KeyCode::Media(MediaKeyCode::TrackNext),
        NamedKey::MediaTrackPrevious => KeyCode::Media(MediaKeyCode::TrackPrevious),
        NamedKey::MediaFastForward => KeyCode::Media(MediaKeyCode::FastForward),
        NamedKey::MediaRewind => KeyCode::Media(MediaKeyCode::Rewind),
        NamedKey::MediaRecord => KeyCode::Media(MediaKeyCode::Record),
        NamedKey::AudioVolumeDown => KeyCode::Media(MediaKeyCode::LowerVolume),
        NamedKey::AudioVolumeUp => KeyCode::Media(MediaKeyCode::RaiseVolume),
        NamedKey::AudioVolumeMute => KeyCode::Media(MediaKeyCode::MuteVolume),

        // Modifier keys emitted as KeyCode::Modifier with left/right
        NamedKey::Shift => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightShift,
                _ => ModifierKeyCode::LeftShift,
            };
            KeyCode::Modifier(side)
        }
        NamedKey::Control => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightControl,
                _ => ModifierKeyCode::LeftControl,
            };
            KeyCode::Modifier(side)
        }
        NamedKey::Alt => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightAlt,
                _ => ModifierKeyCode::LeftAlt,
            };
            KeyCode::Modifier(side)
        }
        NamedKey::Super => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightSuper,
                _ => ModifierKeyCode::LeftSuper,
            };
            KeyCode::Modifier(side)
        }
        NamedKey::Hyper => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightHyper,
                _ => ModifierKeyCode::LeftHyper,
            };
            KeyCode::Modifier(side)
        }
        NamedKey::Meta => {
            let side = match location {
                KeyLocation::Right => ModifierKeyCode::RightMeta,
                _ => ModifierKeyCode::LeftMeta,
            };
            KeyCode::Modifier(side)
        }

        // All other named keys — skip
        _ => return None,
    })
}

/// Translate a winit mouse button to the service's [`MouseButton`].
///
/// `None` for buttons a terminal grid cannot express (back/forward).
pub fn translate_mouse_button(button: WinitMouseButton) -> Option<MouseButton> {
    match button {
        WinitMouseButton::Left => Some(MouseButton::Left),
        WinitMouseButton::Right => Some(MouseButton::Right),
        WinitMouseButton::Middle => Some(MouseButton::Middle),
        _ => None,
    }
}

/// Convert pixel coordinates to terminal cell coordinates.
pub fn pixel_to_cell(pixel: (f64, f64), cell_size: (f64, f64)) -> (u16, u16) {
    let col = (pixel.0 / cell_size.0.max(1.0)) as u16;
    let row = (pixel.1 / cell_size.1.max(1.0)) as u16;
    (col, row)
}

/// Convert window pixel dimensions to terminal grid dimensions (cols, rows).
pub fn cell_dimensions_to_grid(width: f64, height: f64, cell_size: (f64, f64)) -> (u16, u16) {
    let cols = (width / cell_size.0.max(1.0)) as u16;
    let rows = (height / cell_size.1.max(1.0)) as u16;
    (cols.max(1), rows.max(1))
}

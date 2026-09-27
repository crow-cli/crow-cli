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
use winit::keyboard::{Key, KeyLocation, NamedKey, PhysicalKey};

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
    translate_key(
        &event.logical_key,
        &event.physical_key,
        event.location,
        modifiers,
        alt_location,
    )
}

/// [`translate_key_event`] expressed over the fields it actually reads.
///
/// `winit::event::KeyEvent` cannot be constructed outside winit — its
/// `platform_specific` field is `pub(crate)` — so this is the seam the tests
/// drive, on the host and in the browser alike.
pub fn translate_key(
    logical_key: &Key,
    physical_key: &PhysicalKey,
    location: KeyLocation,
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
                    let base =
                        physical_key_to_base_char(physical_key, modifiers.contains(KeyModifiers::SHIFT));
                    (modifiers, base)
                }
                _ => (modifiers, None),
            }
        } else {
            (modifiers, None)
        };

    let code = match logical_key {
        Key::Named(named) => translate_named_key(named, &location, effective_modifiers)?,
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

// ---------------------------------------------------------------------------
// Tests — lifted from fresh-gui (lib.rs:1013-1396) and extended over the
// `translate_key` seam. One body, two harnesses: `#[test]` on the host and
// `#[wasm_bindgen_test]` in a real browser, because the whole claim of this
// crate is that the translation behaves identically in both runtimes.
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use winit::keyboard::{KeyCode as WinitKeyCode, NativeKey, NativeKeyCode};

    macro_rules! input_test {
        ($name:ident, $body:block) => {
            #[cfg(not(target_arch = "wasm32"))]
            #[test]
            fn $name() $body

            #[cfg(target_arch = "wasm32")]
            #[wasm_bindgen_test::wasm_bindgen_test]
            fn $name() $body
        };
    }

    /// A physical key for the `translate_key` seam; the logical key decides the
    /// translation, so any valid physical key does.
    fn phys(code: WinitKeyCode) -> PhysicalKey {
        PhysicalKey::Code(code)
    }

    input_test!(
        named_key_navigation,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::ArrowUp, &loc, mods), Some(KeyCode::Up));
            assert_eq!(translate_named_key(&NamedKey::ArrowDown, &loc, mods), Some(KeyCode::Down));
            assert_eq!(translate_named_key(&NamedKey::ArrowLeft, &loc, mods), Some(KeyCode::Left));
            assert_eq!(translate_named_key(&NamedKey::ArrowRight, &loc, mods), Some(KeyCode::Right));
            assert_eq!(translate_named_key(&NamedKey::Home, &loc, mods), Some(KeyCode::Home));
            assert_eq!(translate_named_key(&NamedKey::End, &loc, mods), Some(KeyCode::End));
            assert_eq!(translate_named_key(&NamedKey::PageUp, &loc, mods), Some(KeyCode::PageUp));
            assert_eq!(translate_named_key(&NamedKey::PageDown, &loc, mods), Some(KeyCode::PageDown));
        }
    );

    input_test!(
        named_key_editing,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::Backspace, &loc, mods), Some(KeyCode::Backspace));
            assert_eq!(translate_named_key(&NamedKey::Delete, &loc, mods), Some(KeyCode::Delete));
            assert_eq!(translate_named_key(&NamedKey::Insert, &loc, mods), Some(KeyCode::Insert));
            assert_eq!(translate_named_key(&NamedKey::Enter, &loc, mods), Some(KeyCode::Enter));
            assert_eq!(translate_named_key(&NamedKey::Escape, &loc, mods), Some(KeyCode::Esc));
            assert_eq!(translate_named_key(&NamedKey::Space, &loc, mods), Some(KeyCode::Char(' ')));
        }
    );

    input_test!(
        tab_and_backtab,
        {
            let loc = KeyLocation::Standard;
            assert_eq!(translate_named_key(&NamedKey::Tab, &loc, KeyModifiers::NONE), Some(KeyCode::Tab));
            assert_eq!(translate_named_key(&NamedKey::Tab, &loc, KeyModifiers::SHIFT), Some(KeyCode::BackTab));
        }
    );

    input_test!(
        function_keys,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::F1, &loc, mods), Some(KeyCode::F(1)));
            assert_eq!(translate_named_key(&NamedKey::F5, &loc, mods), Some(KeyCode::F(5)));
            assert_eq!(translate_named_key(&NamedKey::F12, &loc, mods), Some(KeyCode::F(12)));
            assert_eq!(translate_named_key(&NamedKey::F24, &loc, mods), Some(KeyCode::F(24)));
            assert_eq!(translate_named_key(&NamedKey::F35, &loc, mods), Some(KeyCode::F(35)));
        }
    );

    input_test!(
        lock_and_misc_keys,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::CapsLock, &loc, mods), Some(KeyCode::CapsLock));
            assert_eq!(translate_named_key(&NamedKey::NumLock, &loc, mods), Some(KeyCode::NumLock));
            assert_eq!(translate_named_key(&NamedKey::ScrollLock, &loc, mods), Some(KeyCode::ScrollLock));
            assert_eq!(translate_named_key(&NamedKey::PrintScreen, &loc, mods), Some(KeyCode::PrintScreen));
            assert_eq!(translate_named_key(&NamedKey::Pause, &loc, mods), Some(KeyCode::Pause));
            assert_eq!(translate_named_key(&NamedKey::ContextMenu, &loc, mods), Some(KeyCode::Menu));
        }
    );

    input_test!(
        modifier_keys_keep_their_side,
        {
            let mods = KeyModifiers::NONE;
            assert_eq!(
                translate_named_key(&NamedKey::Shift, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftShift))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Control, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftControl))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Alt, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftAlt))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Super, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftSuper))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Hyper, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftHyper))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Meta, &KeyLocation::Left, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::LeftMeta))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Shift, &KeyLocation::Right, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::RightShift))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Control, &KeyLocation::Right, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::RightControl))
            );
            assert_eq!(
                translate_named_key(&NamedKey::Super, &KeyLocation::Right, mods),
                Some(KeyCode::Modifier(ModifierKeyCode::RightSuper))
            );
        }
    );

    input_test!(
        media_keys,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::MediaPlay, &loc, mods), Some(KeyCode::Media(MediaKeyCode::Play)));
            assert_eq!(translate_named_key(&NamedKey::MediaPause, &loc, mods), Some(KeyCode::Media(MediaKeyCode::Pause)));
            assert_eq!(translate_named_key(&NamedKey::MediaPlayPause, &loc, mods), Some(KeyCode::Media(MediaKeyCode::PlayPause)));
            assert_eq!(translate_named_key(&NamedKey::MediaStop, &loc, mods), Some(KeyCode::Media(MediaKeyCode::Stop)));
            assert_eq!(translate_named_key(&NamedKey::AudioVolumeUp, &loc, mods), Some(KeyCode::Media(MediaKeyCode::RaiseVolume)));
            assert_eq!(translate_named_key(&NamedKey::AudioVolumeDown, &loc, mods), Some(KeyCode::Media(MediaKeyCode::LowerVolume)));
            assert_eq!(translate_named_key(&NamedKey::AudioVolumeMute, &loc, mods), Some(KeyCode::Media(MediaKeyCode::MuteVolume)));
        }
    );

    input_test!(
        unknown_named_key_is_dropped,
        {
            let loc = KeyLocation::Standard;
            let mods = KeyModifiers::NONE;
            assert_eq!(translate_named_key(&NamedKey::BrowserBack, &loc, mods), None);
            assert_eq!(translate_named_key(&NamedKey::LaunchMail, &loc, mods), None);
        }
    );

    input_test!(
        modifiers_none,
        {
            let mods = winit::keyboard::ModifiersState::empty();
            assert_eq!(translate_modifiers(&mods), KeyModifiers::NONE);
        }
    );

    input_test!(
        modifiers_all,
        {
            let mods = winit::keyboard::ModifiersState::SHIFT
                | winit::keyboard::ModifiersState::CONTROL
                | winit::keyboard::ModifiersState::ALT
                | winit::keyboard::ModifiersState::SUPER;
            let result = translate_modifiers(&mods);
            assert!(result.contains(KeyModifiers::SHIFT));
            assert!(result.contains(KeyModifiers::CONTROL));
            assert!(result.contains(KeyModifiers::ALT));
            assert!(result.contains(KeyModifiers::SUPER));
        }
    );

    input_test!(
        modifiers_single,
        {
            assert_eq!(translate_modifiers(&winit::keyboard::ModifiersState::CONTROL), KeyModifiers::CONTROL);
            assert_eq!(translate_modifiers(&winit::keyboard::ModifiersState::ALT), KeyModifiers::ALT);
            assert_eq!(translate_modifiers(&winit::keyboard::ModifiersState::SUPER), KeyModifiers::SUPER);
        }
    );

    input_test!(
        mouse_buttons,
        {
            assert_eq!(translate_mouse_button(WinitMouseButton::Left), Some(MouseButton::Left));
            assert_eq!(translate_mouse_button(WinitMouseButton::Right), Some(MouseButton::Right));
            assert_eq!(translate_mouse_button(WinitMouseButton::Middle), Some(MouseButton::Middle));
            // Buttons a terminal grid cannot express.
            assert_eq!(translate_mouse_button(WinitMouseButton::Back), None);
            assert_eq!(translate_mouse_button(WinitMouseButton::Forward), None);
            assert_eq!(translate_mouse_button(WinitMouseButton::Other(42)), None);
        }
    );

    input_test!(
        pixel_to_cell_basic,
        {
            let cell_size = (10.0, 20.0);
            assert_eq!(pixel_to_cell((0.0, 0.0), cell_size), (0, 0));
            assert_eq!(pixel_to_cell((10.0, 20.0), cell_size), (1, 1));
            assert_eq!(pixel_to_cell((25.0, 45.0), cell_size), (2, 2));
            assert_eq!(pixel_to_cell((99.0, 199.0), cell_size), (9, 9));
        }
    );

    input_test!(
        pixel_to_cell_zero_cell_size,
        {
            // A degenerate cell size must not divide by zero.
            assert_eq!(pixel_to_cell((100.0, 100.0), (0.0, 0.0)), (100, 100));
        }
    );

    // Named apart from the function under test: a test fn called
    // `cell_dimensions_to_grid` shadows it for every call in this module.
    input_test!(
        grid_from_cell_dimensions,
        {
            let (cols, rows) = cell_dimensions_to_grid(1280.0, 800.0, (14.4, 28.8));
            assert_eq!(cols, 88);
            assert_eq!(rows, 27);
        }
    );

    input_test!(
        grid_from_cell_dimensions_minimum,
        {
            let (cols, rows) = cell_dimensions_to_grid(1.0, 1.0, (14.4, 28.8));
            assert_eq!(cols, 1);
            assert_eq!(rows, 1);
        }
    );

    input_test!(
        grid_from_cell_dimensions_zero_size,
        {
            let (cols, rows) = cell_dimensions_to_grid(0.0, 0.0, (14.4, 28.8));
            assert_eq!(cols, 1);
            assert_eq!(rows, 1);
        }
    );

    input_test!(
        base_char_letters,
        {
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::KeyA), false), Some('a'));
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::KeyZ), false), Some('z'));
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::KeyF), true), Some('F'));
        }
    );

    input_test!(
        base_char_digits,
        {
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Digit0), false), Some('0'));
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Digit9), false), Some('9'));
            // Shift does not turn a digit into its punctuation on this path.
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Digit5), true), Some('5'));
        }
    );

    input_test!(
        base_char_punctuation,
        {
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Comma), false), Some(','));
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Slash), false), Some('/'));
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Backquote), false), Some('`'));
        }
    );

    input_test!(
        base_char_unknown_is_none,
        {
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Enter), false), None);
            assert_eq!(physical_key_to_base_char(&phys(WinitKeyCode::Space), false), None);
        }
    );

    // --- the seam the runner actually calls -------------------------------

    input_test!(
        character_key_becomes_a_press,
        {
            let ev = translate_key(
                &Key::Character("a".into()),
                &phys(WinitKeyCode::KeyA),
                KeyLocation::Standard,
                KeyModifiers::NONE,
                None,
            )
            .expect("character key");
            assert_eq!(ev.code, KeyCode::Char('a'));
            assert_eq!(ev.modifiers, KeyModifiers::NONE);
            assert_eq!(ev.kind, KeyEventKind::Press);
            assert_eq!(ev.state, KeyEventState::NONE);
        }
    );

    input_test!(
        shifted_character_keeps_its_modifiers,
        {
            let ev = translate_key(
                &Key::Character("A".into()),
                &phys(WinitKeyCode::KeyA),
                KeyLocation::Standard,
                KeyModifiers::SHIFT,
                None,
            )
            .expect("shifted character");
            assert_eq!(ev.code, KeyCode::Char('A'));
            assert_eq!(ev.modifiers, KeyModifiers::SHIFT);
        }
    );

    input_test!(
        shift_tab_is_backtab,
        {
            let ev = translate_key(
                &Key::Character("\t".into()),
                &phys(WinitKeyCode::Tab),
                KeyLocation::Standard,
                KeyModifiers::SHIFT,
                None,
            )
            .expect("shift-tab");
            assert_eq!(ev.code, KeyCode::BackTab);
        }
    );

    input_test!(
        named_keys_go_through_the_table,
        {
            let ev = translate_key(
                &Key::Named(NamedKey::Escape),
                &phys(WinitKeyCode::Escape),
                KeyLocation::Standard,
                KeyModifiers::NONE,
                None,
            )
            .expect("escape");
            assert_eq!(ev.code, KeyCode::Esc);
        }
    );

    input_test!(
        dead_and_unidentified_keys_are_dropped,
        {
            // A dead key is a composition in progress, not input; winit reports
            // `Dead(None)` on the web.
            assert_eq!(
                translate_key(
                    &Key::Dead(None),
                    &phys(WinitKeyCode::Quote),
                    KeyLocation::Standard,
                    KeyModifiers::NONE,
                    None,
                ),
                None
            );
            assert_eq!(
                translate_key(
                    &Key::Unidentified(NativeKey::Unidentified),
                    &PhysicalKey::Unidentified(NativeKeyCode::Unidentified),
                    KeyLocation::Standard,
                    KeyModifiers::NONE,
                    None,
                ),
                None
            );
        }
    );

    input_test!(
        empty_character_is_dropped,
        {
            assert_eq!(
                translate_key(
                    &Key::Character("".into()),
                    &phys(WinitKeyCode::Space),
                    KeyLocation::Standard,
                    KeyModifiers::NONE,
                    None,
                ),
                None
            );
        }
    );

    input_test!(
        modifier_side_survives_the_seam,
        {
            let ev = translate_key(
                &Key::Named(NamedKey::Shift),
                &phys(WinitKeyCode::ShiftRight),
                KeyLocation::Right,
                KeyModifiers::SHIFT,
                None,
            )
            .expect("right shift");
            assert_eq!(ev.code, KeyCode::Modifier(ModifierKeyCode::RightShift));
        }
    );

    input_test!(
        alt_composition_is_only_special_cased_on_macos,
        {
            // Left Alt on macOS composes an international character, so the
            // runner strips ALT and treats it as text. Everywhere else Alt is
            // just a shortcut modifier and must survive untouched.
            let ev = translate_key(
                &Key::Character("a".into()),
                &phys(WinitKeyCode::KeyA),
                KeyLocation::Standard,
                KeyModifiers::ALT,
                Some(KeyLocation::Left),
            )
            .expect("alt-a");
            assert_eq!(ev.code, KeyCode::Char('a'));
            if cfg!(target_os = "macos") {
                assert_eq!(ev.modifiers, KeyModifiers::NONE);
            } else {
                assert_eq!(ev.modifiers, KeyModifiers::ALT);
            }
        }
    );
}


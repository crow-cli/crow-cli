//! crossterm-shaped event types.
//!
//! crow's whole input stack (`App::handle(AppEvent::Term(..))`, the composer,
//! the keymap layer) speaks crossterm's `KeyEvent` / `MouseEvent`. crossterm
//! 0.29 itself does not compile for `wasm32-unknown-unknown` — its
//! `terminal/sys.rs` only has `#[cfg(unix)]` and `#[cfg(windows)]` branches —
//! and ratatui 0.30 has no backend-neutral event types of its own (they live in
//! `ratatui-crossterm`, i.e. they *are* crossterm's).
//!
//! So the service owns the shapes: the same enums, bitflags and structs,
//! minus every platform-specific note, minus the terminal plumbing. The runner
//! translates winit events into these on both runtimes, and the native adapter
//! converts them into real `crossterm::event` values for crow's `App` — one
//! input vocabulary, two hosts.
//!
//! Shapes mirror crossterm 0.29 (MIT) so that conversion is a field-for-field
//! copy and existing crow key-handling code reads unchanged.

use bitflags::bitflags;

/// Represents a key.
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum KeyCode {
    /// Backspace key (Delete on macOS, Backspace on other platforms).
    Backspace,
    /// Enter key.
    Enter,
    /// Left arrow key.
    Left,
    /// Right arrow key.
    Right,
    /// Up arrow key.
    Up,
    /// Down arrow key.
    Down,
    /// Home key.
    Home,
    /// End key.
    End,
    /// Page up key.
    PageUp,
    /// Page down key.
    PageDown,
    /// Tab key.
    Tab,
    /// Shift + Tab key.
    BackTab,
    /// Delete key. (Fn+Delete on macOS, Delete on other platforms)
    Delete,
    /// Insert key.
    Insert,
    /// F key. `KeyCode::F(1)` represents F1, etc.
    F(u8),
    /// A character. `KeyCode::Char('c')` represents `c`, etc.
    Char(char),
    /// Null.
    Null,
    /// Escape key.
    Esc,
    /// Caps Lock key.
    CapsLock,
    /// Scroll Lock key.
    ScrollLock,
    /// Num Lock key.
    NumLock,
    /// Print Screen key.
    PrintScreen,
    /// Pause key.
    Pause,
    /// Menu key.
    Menu,
    /// The "Begin" key (often mapped to the 5 key when Num Lock is on).
    KeypadBegin,
    /// A media key.
    Media(MediaKeyCode),
    /// A modifier key.
    Modifier(ModifierKeyCode),
}

/// Represents a media key (as part of [`KeyCode::Media`]).
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum MediaKeyCode {
    /// Play media key.
    Play,
    /// Pause media key.
    Pause,
    /// Play/Pause media key.
    PlayPause,
    /// Reverse media key.
    Reverse,
    /// Stop media key.
    Stop,
    /// Fast-forward media key.
    FastForward,
    /// Rewind media key.
    Rewind,
    /// Next-track media key.
    TrackNext,
    /// Previous-track media key.
    TrackPrevious,
    /// Record media key.
    Record,
    /// Lower-volume media key.
    LowerVolume,
    /// Raise-volume media key.
    RaiseVolume,
    /// Mute media key.
    MuteVolume,
}

/// Represents a modifier key (as part of [`KeyCode::Modifier`]).
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum ModifierKeyCode {
    /// Left Shift key.
    LeftShift,
    /// Left Control key.
    LeftControl,
    /// Left Alt key. (Option on macOS)
    LeftAlt,
    /// Left Super key. (Command on macOS, Windows on Windows)
    LeftSuper,
    /// Left Hyper key.
    LeftHyper,
    /// Left Meta key.
    LeftMeta,
    /// Right Shift key.
    RightShift,
    /// Right Control key.
    RightControl,
    /// Right Alt key. (Option on macOS)
    RightAlt,
    /// Right Super key. (Command on macOS, Windows on Windows)
    RightSuper,
    /// Right Hyper key.
    RightHyper,
    /// Right Meta key.
    RightMeta,
    /// Iso Level3 Shift key.
    IsoLevel3Shift,
    /// Iso Level5 Shift key.
    IsoLevel5Shift,
}

/// Represents a keyboard event kind.
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum KeyEventKind {
    /// Key press.
    Press,
    /// Key repeat (auto-repeat while held).
    Repeat,
    /// Key release.
    Release,
}

bitflags! {
    /// Represents extra state about the key event (keypad, lock keys).
    #[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
    pub struct KeyEventState: u8 {
        /// The key event origins from the keypad.
        const KEYPAD = 0b0000_0001;
        /// Caps Lock was enabled for this key event.
        const CAPS_LOCK = 0b0000_0010;
        /// Num Lock was enabled for this key event.
        const NUM_LOCK = 0b0000_0100;
        /// No state.
        const NONE = 0b0000_0000;
    }
}

bitflags! {
    /// Represents key modifiers (shift, control, alt, etc.).
    #[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
    pub struct KeyModifiers: u8 {
        /// Shift.
        const SHIFT = 0b0000_0001;
        /// Control.
        const CONTROL = 0b0000_0010;
        /// Alt (Option on macOS).
        const ALT = 0b0000_0100;
        /// Super (Command on macOS, Windows on Windows).
        const SUPER = 0b0000_1000;
        /// Hyper.
        const HYPER = 0b0001_0000;
        /// Meta.
        const META = 0b0010_0000;
        /// No modifiers.
        const NONE = 0b0000_0000;
    }
}

/// Represents a key event.
#[derive(Debug, PartialOrd, Clone, Copy, PartialEq, Eq, Hash)]
pub struct KeyEvent {
    /// The key itself.
    pub code: KeyCode,
    /// Additional key modifiers.
    pub modifiers: KeyModifiers,
    /// Kind of event (press / repeat / release).
    pub kind: KeyEventKind,
    /// Extra keyboard state.
    pub state: KeyEventState,
}

impl KeyEvent {
    /// A key press with no extra state.
    pub const fn new(code: KeyCode, modifiers: KeyModifiers) -> KeyEvent {
        KeyEvent {
            code,
            modifiers,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    /// A key event of an explicit kind with no extra state.
    pub const fn new_with_kind(
        code: KeyCode,
        modifiers: KeyModifiers,
        kind: KeyEventKind,
    ) -> KeyEvent {
        KeyEvent {
            code,
            modifiers,
            kind,
            state: KeyEventState::NONE,
        }
    }

    /// A key event of an explicit kind and state.
    pub const fn new_with_kind_and_state(
        code: KeyCode,
        modifiers: KeyModifiers,
        kind: KeyEventKind,
        state: KeyEventState,
    ) -> KeyEvent {
        KeyEvent {
            code,
            modifiers,
            kind,
            state,
        }
    }
}

/// Represents a mouse button.
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum MouseButton {
    /// Left mouse button.
    Left,
    /// Right mouse button.
    Right,
    /// Middle mouse button.
    Middle,
}

/// A mouse event kind.
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub enum MouseEventKind {
    /// Pressed mouse button.
    Down(MouseButton),
    /// Released mouse button.
    Up(MouseButton),
    /// Moved the mouse cursor while pressing the contained mouse button.
    Drag(MouseButton),
    /// Moved the mouse cursor while not pressing a mouse button.
    Moved,
    /// Scrolled mouse wheel downwards (towards the user).
    ScrollDown,
    /// Scrolled mouse wheel upwards (away from the user).
    ScrollUp,
    /// Scrolled mouse wheel left.
    ScrollLeft,
    /// Scrolled mouse wheel right.
    ScrollRight,
}

/// A mouse event, in terminal cell coordinates.
#[derive(Debug, PartialOrd, PartialEq, Eq, Clone, Copy, Hash)]
pub struct MouseEvent {
    /// The kind of mouse event.
    pub kind: MouseEventKind,
    /// The column the event occurred on.
    pub column: u16,
    /// The row the event occurred on.
    pub row: u16,
    /// The key modifiers active when the event occurred.
    pub modifiers: KeyModifiers,
}

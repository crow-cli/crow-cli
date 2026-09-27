//! The `GuiApplication` adapter: crow's `App` inside crow-gui's window.
//!
//! crow's input stack speaks crossterm; crow-gui delivers its own
//! crossterm-*shaped* types (the service cannot depend on crossterm, which does
//! not compile for wasm32). The shapes mirror crossterm 0.29 field for field,
//! so the conversion below is a copy, not a translation — one input vocabulary,
//! two hosts.

use std::sync::mpsc;
use std::time::{Duration, Instant};

use anyhow::Result;
use crow_gui::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers, MediaKeyCode, ModifierKeyCode,
    MouseButton, MouseEvent, MouseEventKind,
};
use crow_gui::GuiApplication;
use crossterm::event::{
    Event as CtEvent, KeyEvent as CtKeyEvent, KeyEventKind as CtKeyEventKind,
    KeyEventState as CtKeyEventState, KeyCode as CtKeyCode, KeyModifiers as CtKeyModifiers,
    MediaKeyCode as CtMediaKeyCode, ModifierKeyCode as CtModifierKeyCode,
    MouseButton as CtMouseButton, MouseEvent as CtMouseEvent, MouseEventKind as CtMouseEventKind,
};
use ratatui::Frame;

use crate::app::App;
use crate::bus::{AppEvent, Cmd};
use crate::controller::Controller;

/// crow's `App`, hosted in a GPU window.
pub(crate) struct CrowApp {
    pub(crate) app: App,
    pub(crate) ctl: Controller,
    pub(crate) bus_rx: mpsc::Receiver<AppEvent>,
    last_tick: Instant,
}

impl CrowApp {
    pub(crate) fn new(app: App, ctl: Controller, bus_rx: mpsc::Receiver<AppEvent>) -> Self {
        Self { app, ctl, bus_rx, last_tick: Instant::now() }
    }
}

impl GuiApplication for CrowApp {
    fn on_key(&mut self, key: KeyEvent) -> Result<()> {
        self.app
            .handle(AppEvent::Term(CtEvent::Key(ct_key(key))), &self.ctl);
        Ok(())
    }

    fn on_mouse(&mut self, mouse: MouseEvent) -> Result<bool> {
        self.app
            .handle(AppEvent::Term(CtEvent::Mouse(ct_mouse(mouse))), &self.ctl);
        Ok(self.app.needs_redraw)
    }

    fn render(&mut self, frame: &mut Frame) {
        crate::ui::draw(frame, &mut self.app);
        // The TTY loop clears this right after `terminal.draw`; the runner only
        // clears its own dirty flag, so the adapter is the one that can.
        self.app.needs_redraw = false;
    }

    fn tick(&mut self) -> Result<bool> {
        // The runner is the only thing that wakes on a timer, so the bus drain
        // lives here. Batched exactly like the TTY loop: a burst of ACP session
        // updates coalesces into one repaint instead of one per event.
        match self.bus_rx.try_recv() {
            Ok(first) => {
                let (batch, _immediate) = crate::collect_event_batch(first, &self.bus_rx);
                for ev in batch {
                    self.app.handle(ev, &self.ctl);
                }
            }
            Err(mpsc::TryRecvError::Disconnected) => self.app.quit = true,
            Err(mpsc::TryRecvError::Empty) => {}
        }
        if self.last_tick.elapsed() >= Duration::from_millis(100) {
            self.app.tick();
            self.last_tick = Instant::now();
        }
        Ok(self.app.needs_redraw)
    }

    fn should_quit(&self) -> bool {
        self.app.quit
    }

    fn resize(&mut self, cols: u16, rows: u16) {
        // Same vocabulary as the TTY: crossterm reports a resize as a terminal
        // event, and scrollback/popup layout key off it.
        self.app
            .handle(AppEvent::Term(CtEvent::Resize(cols, rows)), &self.ctl);
    }

    fn on_close(&mut self) {
        self.ctl.send(Cmd::Shutdown);
    }
}

// ---------------------------------------------------------------------------
// crow-gui event shapes -> crossterm 0.29 (field-for-field)
// ---------------------------------------------------------------------------

pub(crate) fn ct_key(ev: KeyEvent) -> CtKeyEvent {
    CtKeyEvent {
        code: ct_code(ev.code),
        modifiers: ct_modifiers(ev.modifiers),
        kind: ct_kind(ev.kind),
        state: ct_state(ev.state),
    }
}

pub(crate) fn ct_mouse(ev: MouseEvent) -> CtMouseEvent {
    CtMouseEvent {
        kind: ct_mouse_kind(ev.kind),
        column: ev.column,
        row: ev.row,
        modifiers: ct_modifiers(ev.modifiers),
    }
}

fn ct_modifiers(mods: KeyModifiers) -> CtKeyModifiers {
    CtKeyModifiers::from_bits_truncate(mods.bits())
}

fn ct_state(state: KeyEventState) -> CtKeyEventState {
    CtKeyEventState::from_bits_truncate(state.bits())
}

fn ct_kind(kind: KeyEventKind) -> CtKeyEventKind {
    match kind {
        KeyEventKind::Press => CtKeyEventKind::Press,
        KeyEventKind::Repeat => CtKeyEventKind::Repeat,
        KeyEventKind::Release => CtKeyEventKind::Release,
    }
}

fn ct_code(code: KeyCode) -> CtKeyCode {
    match code {
        KeyCode::Backspace => CtKeyCode::Backspace,
        KeyCode::Enter => CtKeyCode::Enter,
        KeyCode::Left => CtKeyCode::Left,
        KeyCode::Right => CtKeyCode::Right,
        KeyCode::Up => CtKeyCode::Up,
        KeyCode::Down => CtKeyCode::Down,
        KeyCode::Home => CtKeyCode::Home,
        KeyCode::End => CtKeyCode::End,
        KeyCode::PageUp => CtKeyCode::PageUp,
        KeyCode::PageDown => CtKeyCode::PageDown,
        KeyCode::Tab => CtKeyCode::Tab,
        KeyCode::BackTab => CtKeyCode::BackTab,
        KeyCode::Delete => CtKeyCode::Delete,
        KeyCode::Insert => CtKeyCode::Insert,
        KeyCode::F(n) => CtKeyCode::F(n),
        KeyCode::Char(c) => CtKeyCode::Char(c),
        KeyCode::Null => CtKeyCode::Null,
        KeyCode::Esc => CtKeyCode::Esc,
        KeyCode::CapsLock => CtKeyCode::CapsLock,
        KeyCode::ScrollLock => CtKeyCode::ScrollLock,
        KeyCode::NumLock => CtKeyCode::NumLock,
        KeyCode::PrintScreen => CtKeyCode::PrintScreen,
        KeyCode::Pause => CtKeyCode::Pause,
        KeyCode::Menu => CtKeyCode::Menu,
        KeyCode::KeypadBegin => CtKeyCode::KeypadBegin,
        KeyCode::Media(m) => CtKeyCode::Media(ct_media(m)),
        KeyCode::Modifier(m) => CtKeyCode::Modifier(ct_modifier(m)),
    }
}

fn ct_media(m: MediaKeyCode) -> CtMediaKeyCode {
    match m {
        MediaKeyCode::Play => CtMediaKeyCode::Play,
        MediaKeyCode::Pause => CtMediaKeyCode::Pause,
        MediaKeyCode::PlayPause => CtMediaKeyCode::PlayPause,
        MediaKeyCode::Reverse => CtMediaKeyCode::Reverse,
        MediaKeyCode::Stop => CtMediaKeyCode::Stop,
        MediaKeyCode::FastForward => CtMediaKeyCode::FastForward,
        MediaKeyCode::Rewind => CtMediaKeyCode::Rewind,
        MediaKeyCode::TrackNext => CtMediaKeyCode::TrackNext,
        MediaKeyCode::TrackPrevious => CtMediaKeyCode::TrackPrevious,
        MediaKeyCode::Record => CtMediaKeyCode::Record,
        MediaKeyCode::LowerVolume => CtMediaKeyCode::LowerVolume,
        MediaKeyCode::RaiseVolume => CtMediaKeyCode::RaiseVolume,
        MediaKeyCode::MuteVolume => CtMediaKeyCode::MuteVolume,
    }
}

fn ct_modifier(m: ModifierKeyCode) -> CtModifierKeyCode {
    match m {
        ModifierKeyCode::LeftShift => CtModifierKeyCode::LeftShift,
        ModifierKeyCode::LeftControl => CtModifierKeyCode::LeftControl,
        ModifierKeyCode::LeftAlt => CtModifierKeyCode::LeftAlt,
        ModifierKeyCode::LeftSuper => CtModifierKeyCode::LeftSuper,
        ModifierKeyCode::LeftHyper => CtModifierKeyCode::LeftHyper,
        ModifierKeyCode::LeftMeta => CtModifierKeyCode::LeftMeta,
        ModifierKeyCode::RightShift => CtModifierKeyCode::RightShift,
        ModifierKeyCode::RightControl => CtModifierKeyCode::RightControl,
        ModifierKeyCode::RightAlt => CtModifierKeyCode::RightAlt,
        ModifierKeyCode::RightSuper => CtModifierKeyCode::RightSuper,
        ModifierKeyCode::RightHyper => CtModifierKeyCode::RightHyper,
        ModifierKeyCode::RightMeta => CtModifierKeyCode::RightMeta,
        ModifierKeyCode::IsoLevel3Shift => CtModifierKeyCode::IsoLevel3Shift,
        ModifierKeyCode::IsoLevel5Shift => CtModifierKeyCode::IsoLevel5Shift,
    }
}

fn ct_mouse_button(b: MouseButton) -> CtMouseButton {
    match b {
        MouseButton::Left => CtMouseButton::Left,
        MouseButton::Right => CtMouseButton::Right,
        MouseButton::Middle => CtMouseButton::Middle,
    }
}

fn ct_mouse_kind(kind: MouseEventKind) -> CtMouseEventKind {
    match kind {
        MouseEventKind::Down(b) => CtMouseEventKind::Down(ct_mouse_button(b)),
        MouseEventKind::Up(b) => CtMouseEventKind::Up(ct_mouse_button(b)),
        MouseEventKind::Drag(b) => CtMouseEventKind::Drag(ct_mouse_button(b)),
        MouseEventKind::Moved => CtMouseEventKind::Moved,
        MouseEventKind::ScrollDown => CtMouseEventKind::ScrollDown,
        MouseEventKind::ScrollUp => CtMouseEventKind::ScrollUp,
        MouseEventKind::ScrollLeft => CtMouseEventKind::ScrollLeft,
        MouseEventKind::ScrollRight => CtMouseEventKind::ScrollRight,
    }
}

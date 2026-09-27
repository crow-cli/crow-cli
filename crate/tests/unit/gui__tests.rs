//! Phase 3.1/3.2: the `CrowApp` adapter and the crossterm conversion it feeds.
//!
//! `GuiApplication` takes no window handle, so the whole adapter is testable on
//! the host: keys and resizes go in as crow-gui shapes, `App::handle` sees
//! crossterm shapes, and the bus drain is a plain channel. What these do NOT
//! cover is the window itself — that needs a display (CONTEXT.md, "Native
//! window verification on the live compositor").

use std::sync::mpsc;
use std::time::Duration;

use crow_gui::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers, MediaKeyCode, ModifierKeyCode,
    MouseButton, MouseEvent, MouseEventKind,
};
use crow_gui::GuiApplication;
use crossterm::event::{
    Event as CtEvent, KeyCode as CtKeyCode, KeyEvent as CtKeyEvent, KeyEventKind as CtKeyEventKind,
    KeyEventState as CtKeyEventState, KeyModifiers as CtKeyModifiers,
    MediaKeyCode as CtMediaKeyCode, ModifierKeyCode as CtModifierKeyCode,
    MouseButton as CtMouseButton, MouseEventKind as CtMouseEventKind,
};

use crate::bus::{AppEvent, Cmd};
use crate::gui::app::{ct_key, ct_mouse, CrowApp};
use crate::runtime::RuntimeConfig;
use crate::theme::Theme;
use crate::app::App;

fn fresh_root() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir().join(format!(
        "crow-gui-adapter-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed),
    ));
    let _ = std::fs::create_dir_all(&dir);
    dir.to_string_lossy().into_owned()
}

/// A `CrowApp` wired to a test controller: the commands it sends land in the
/// returned receiver instead of a live agent.
fn test_crow_app() -> (CrowApp, mpsc::Receiver<Cmd>, mpsc::Sender<AppEvent>) {
    let cfg = RuntimeConfig {
        bin: "crow-runtime".into(),
        cordis: "cordis".into(),
        workspace: "/tmp".into(),
        session_root: fresh_root(),
        provider: "deepseek".into(),
        model: "deepseek-chat".into(),
        max_tokens: None,
        base_url: None,
        api_key: None,
        startup_session: None,
    };
    let (bus_tx, bus_rx) = mpsc::channel();
    let app = App::new(
        Some(Theme::dark()),
        cfg,
        "crow-gui-test".into(),
        true,
        false,
        bus_tx.clone(),
    );
    let (ctl, cmds) = crate::controller::tests::test_controller();
    (CrowApp::new(app, ctl, bus_rx), cmds, bus_tx)
}

// ---------------------------------------------------------------------------
// The conversion: crow-gui shapes are crossterm 0.29 shapes, field for field
// ---------------------------------------------------------------------------

#[test]
fn key_conversion_is_field_for_field() {
    let ev = KeyEvent {
        code: KeyCode::Char('a'),
        modifiers: KeyModifiers::CONTROL | KeyModifiers::ALT,
        kind: KeyEventKind::Repeat,
        state: KeyEventState::KEYPAD,
    };
    let ct = ct_key(ev);
    assert_eq!(ct.code, CtKeyCode::Char('a'));
    assert_eq!(ct.modifiers, CtKeyModifiers::CONTROL | CtKeyModifiers::ALT);
    assert_eq!(ct.kind, CtKeyEventKind::Repeat);
    assert_eq!(ct.state, CtKeyEventState::KEYPAD);
}

#[test]
fn every_key_code_variant_survives_the_conversion() {
    let cases: Vec<(KeyCode, CtKeyCode)> = vec![
        (KeyCode::Backspace, CtKeyCode::Backspace),
        (KeyCode::Enter, CtKeyCode::Enter),
        (KeyCode::Left, CtKeyCode::Left),
        (KeyCode::Right, CtKeyCode::Right),
        (KeyCode::Up, CtKeyCode::Up),
        (KeyCode::Down, CtKeyCode::Down),
        (KeyCode::Home, CtKeyCode::Home),
        (KeyCode::End, CtKeyCode::End),
        (KeyCode::PageUp, CtKeyCode::PageUp),
        (KeyCode::PageDown, CtKeyCode::PageDown),
        (KeyCode::Tab, CtKeyCode::Tab),
        (KeyCode::BackTab, CtKeyCode::BackTab),
        (KeyCode::Delete, CtKeyCode::Delete),
        (KeyCode::Insert, CtKeyCode::Insert),
        (KeyCode::F(12), CtKeyCode::F(12)),
        (KeyCode::Char('ü'), CtKeyCode::Char('ü')),
        (KeyCode::Null, CtKeyCode::Null),
        (KeyCode::Esc, CtKeyCode::Esc),
        (KeyCode::CapsLock, CtKeyCode::CapsLock),
        (KeyCode::ScrollLock, CtKeyCode::ScrollLock),
        (KeyCode::NumLock, CtKeyCode::NumLock),
        (KeyCode::PrintScreen, CtKeyCode::PrintScreen),
        (KeyCode::Pause, CtKeyCode::Pause),
        (KeyCode::Menu, CtKeyCode::Menu),
        (KeyCode::KeypadBegin, CtKeyCode::KeypadBegin),
        (KeyCode::Media(MediaKeyCode::MuteVolume), CtKeyCode::Media(CtMediaKeyCode::MuteVolume)),
        (
            KeyCode::Modifier(ModifierKeyCode::RightSuper),
            CtKeyCode::Modifier(CtModifierKeyCode::RightSuper),
        ),
    ];
    for (gui, ct) in cases {
        let ev = KeyEvent::new(gui, KeyModifiers::NONE);
        assert_eq!(ct_key(ev).code, ct, "{gui:?}");
    }
}

#[test]
fn mouse_conversion_carries_cell_button_and_modifiers() {
    let ev = MouseEvent {
        kind: MouseEventKind::Drag(MouseButton::Right),
        column: 12,
        row: 34,
        modifiers: KeyModifiers::SHIFT,
    };
    let ct = ct_mouse(ev);
    assert_eq!(ct.kind, CtMouseEventKind::Drag(CtMouseButton::Right));
    assert_eq!((ct.column, ct.row), (12, 34));
    assert_eq!(ct.modifiers, CtKeyModifiers::SHIFT);
}

// ---------------------------------------------------------------------------
// The adapter: crow-gui callbacks reach crow's App unchanged
// ---------------------------------------------------------------------------

#[test]
fn on_key_reaches_the_app() {
    let (mut crow, _cmds, _bus) = test_crow_app();
    crow.app.needs_redraw = false;
    crow.on_key(KeyEvent::new(KeyCode::Char('h'), KeyModifiers::NONE)).unwrap();
    assert!(crow.app.needs_redraw, "typing into the composer dirties the frame");
}

#[test]
fn resize_arrives_as_a_terminal_event() {
    let (mut crow, _cmds, _bus) = test_crow_app();
    crow.app.needs_redraw = false;
    crow.resize(100, 40);
    assert!(crow.app.needs_redraw, "the TTY loop sees Event::Resize; so must the window");
}

#[test]
fn on_close_shuts_the_controller_down() {
    let (mut crow, cmds, _bus) = test_crow_app();
    crow.on_close();
    let cmd = cmds.recv_timeout(Duration::from_secs(2)).expect("a command");
    assert!(matches!(cmd, Cmd::Shutdown), "got {cmd:?}");
}

#[test]
fn should_quit_follows_the_app() {
    let (mut crow, _cmds, _bus) = test_crow_app();
    assert!(!crow.should_quit());
    crow.app.quit = true;
    assert!(crow.should_quit());
}

#[test]
fn tick_drains_the_bus() {
    let (mut crow, _cmds, bus) = test_crow_app();
    // The termination handler's event is what SIGTERM puts on the bus; the
    // drain is the only path by which it can reach the app in a window.
    bus.send(AppEvent::Terminate).unwrap();
    assert!(!crow.app.quit, "nothing has looked at the bus yet");
    crow.tick().unwrap();
    assert!(crow.app.quit, "the drain delivered Terminate");
}

#[test]
fn tick_reports_the_redraw_the_drain_caused() {
    let (mut crow, _cmds, bus) = test_crow_app();
    crow.app.needs_redraw = false;
    assert!(!crow.tick().unwrap(), "quiet bus, quiet app: no repaint");
    bus.send(AppEvent::Term(CtEvent::Key(CtKeyEvent::new(
        CtKeyCode::Char('x'),
        CtKeyModifiers::NONE,
    ))))
    .unwrap();
    assert!(crow.tick().unwrap(), "a drained key press dirties the frame");
}

#[test]
fn render_clears_the_redraw_flag_like_the_tty_loop() {
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    let (mut crow, _cmds, _bus) = test_crow_app();
    crow.app.needs_redraw = true;
    let mut terminal = Terminal::new(TestBackend::new(80, 24)).expect("test terminal");
    terminal.draw(|f| crow.render(f)).expect("draw frame");
    assert!(!crow.app.needs_redraw, "a painted frame is not a dirty frame");
    let buf = terminal.backend().buffer().clone();
    let row0: String = (0..80).map(|x| buf[(x, 0)].symbol()).collect();
    assert!(!row0.trim().is_empty(), "the real UI painted row 0: {row0:?}");
}

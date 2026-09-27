//! Phase 1.3: the native `--gui` window's hosted application.
//!
//! `crow_gui::GuiApplication` takes no window handle, so the whole adapter is
//! testable on the host without a compositor: keys and resizes go in, `render`
//! goes into a `TestBackend` exactly like the TUI's own layout tests. What
//! these do NOT cover is the window itself — that is `tests/gui_launch.rs`,
//! which needs a display.

use crate::gui::PlaceholderApp;
use crow_gui::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use crow_gui::GuiApplication;

/// Render one frame through a `TestBackend` and return it as text, the same way
/// `ui::dump_frame` does for the TUI.
fn rendered(app: &mut PlaceholderApp, width: u16, height: u16) -> String {
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("test terminal");
    terminal.draw(|f| app.render(f)).expect("draw frame");
    let buf = terminal.backend().buffer().clone();
    let mut out = String::new();
    for row in 0..buf.area.height {
        let line: String = (0..buf.area.width).map(|col| buf[(col, row)].symbol()).collect();
        out.push_str(line.trim_end());
        out.push('\n');
    }
    out
}

#[test]
fn esc_quits_the_window() {
    let mut app = PlaceholderApp::new(80, 24);
    assert!(!app.should_quit(), "fresh window stays open");
    app.on_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)).unwrap();
    assert!(app.should_quit(), "Esc is the way out");
}

#[test]
fn q_quits_the_window() {
    let mut app = PlaceholderApp::new(80, 24);
    app.on_key(KeyEvent::new(KeyCode::Char('q'), KeyModifiers::NONE)).unwrap();
    assert!(app.should_quit());
}

#[test]
fn unrelated_keys_do_not_quit() {
    let mut app = PlaceholderApp::new(80, 24);
    for code in [
        KeyCode::Char('x'),
        KeyCode::Enter,
        KeyCode::Up,
        KeyCode::Char('Q'), // capital Q is Ctrl/Cmd+q territory, not a bare quit
        KeyCode::F(1),
    ] {
        app.on_key(KeyEvent::new(code, KeyModifiers::NONE)).unwrap();
    }
    assert!(!app.should_quit());
}

#[test]
fn only_the_press_quits() {
    // winit delivers Press, Repeat and Release for one physical keystroke; the
    // TUI acts on Press only, so the window must too or a single Esc counts
    // three times once a real App is behind this.
    let mut app = PlaceholderApp::new(80, 24);
    for kind in [KeyEventKind::Release, KeyEventKind::Repeat] {
        app.on_key(KeyEvent::new_with_kind(KeyCode::Esc, KeyModifiers::NONE, kind))
            .unwrap();
        assert!(!app.should_quit(), "{kind:?} must not quit");
    }
    app.on_key(KeyEvent::new_with_kind(KeyCode::Esc, KeyModifiers::NONE, KeyEventKind::Press))
        .unwrap();
    assert!(app.should_quit());
}

#[test]
fn mouse_needs_no_repaint_yet() {
    let mut app = PlaceholderApp::new(80, 24);
    let ev = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: 4,
        row: 2,
        modifiers: KeyModifiers::NONE,
    };
    assert!(!app.on_mouse(ev).unwrap(), "nothing on screen tracks the mouse yet");
    assert!(!app.should_quit());
}

#[test]
fn tick_does_not_request_a_repaint() {
    // The placeholder has no animation and no event bus, so it must not keep
    // the runner redrawing at 60fps. Phase 3.2 replaces this with the drain.
    let mut app = PlaceholderApp::new(80, 24);
    assert!(!app.tick().unwrap());
}

#[test]
fn the_frame_is_a_bordered_panel_that_says_how_to_leave() {
    let mut app = PlaceholderApp::new(80, 24);
    let text = rendered(&mut app, 60, 12);
    let rows: Vec<&str> = text.lines().collect();
    assert!(rows[0].starts_with('┌') && rows[0].ends_with('┐'), "top border: {:?}", rows[0]);
    assert!(
        rows[11].starts_with('└') && rows[11].ends_with('┘'),
        "bottom border: {:?}",
        rows[11]
    );
    assert!(rows[0].contains("phase 1.3"), "title: {:?}", rows[0]);
    assert!(text.contains("crow"), "wordmark: {text:?}");
    assert!(text.contains("native GPU window"), "runtime label: {text:?}");
    assert!(text.contains("Esc or q to quit"), "quit hint: {text:?}");
}

#[test]
fn resize_shows_up_in_the_frame() {
    // The runner is the only thing that learns the new pixel size; the app has
    // to take the grid it is handed and reflect it, or a resized window paints
    // a stale layout.
    let mut app = PlaceholderApp::new(80, 24);
    assert!(rendered(&mut app, 60, 12).contains("grid 80x24"));
    app.resize(40, 10);
    assert!(rendered(&mut app, 40, 10).contains("grid 40x10"));
}

#[test]
fn on_close_is_quiet() {
    // Phase 4.2 gives this a Cmd::Shutdown; until then it must not panic or
    // flip quit (the runner already exits on CloseRequested).
    let mut app = PlaceholderApp::new(80, 24);
    app.on_close();
    assert!(!app.should_quit());
}

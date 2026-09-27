//! The browser runtime: crow-gui's service hosted in a DOM canvas.
//!
//! This bin is the web half of "one UI service, two runtimes" — the native
//! `--gui` window runs the very same [`crow_gui::run`] with a different surface.
//! Today it hosts a paint probe ([`ProbeApp`]) rather than crow's real `App`
//! (that adapter is phase 3); the point of the bin right now is that the whole
//! stack — winit event loop, wgpu/WebGL2 surface, ratatui render, font atlas —
//! runs in a browser and can be asserted on end-to-end by
//! `tests/e2e/test_web_paint_live.py`.
//!
//! Build + stage with `crate/scripts/build-web.sh`, serve `crate/web/`.

use anyhow::Result;
use ratatui::prelude::*;
use ratatui::widgets::{Block, Paragraph};

use crow_gui::event::{KeyCode, KeyEvent, MouseEvent};
use crow_gui::{GuiApplication, GuiConfig};

/// Publish a value on `window.__crowProbe[key]` so the Playwright harness can
/// assert deterministically instead of sleeping.
fn publish(key: &str, value: &wasm_bindgen::JsValue) {
    let Some(window) = web_sys::window() else {
        return;
    };
    let holder = js_sys::Reflect::get(&window, &"__crowProbe".into()).ok();
    let holder = match holder {
        Some(h) if h.is_object() => h,
        _ => {
            let obj = js_sys::Object::new();
            let _ = js_sys::Reflect::set(&window, &"__crowProbe".into(), &obj);
            obj.into()
        }
    };
    let _ = js_sys::Reflect::set(&holder, &key.into(), value);
}

/// The hosted application: paints a fixed palette and counts frames.
struct ProbeApp {
    frames: u32,
    quit: bool,
}

impl ProbeApp {
    fn new(cols: u16, rows: u16) -> Self {
        publish("cols", &cols.into());
        publish("rows", &rows.into());
        publish("frames", &0.into());
        publish("stage", &"ready".into());
        publish("ready", &true.into());
        Self { frames: 0, quit: false }
    }
}

impl GuiApplication for ProbeApp {
    fn on_key(&mut self, key: KeyEvent) -> Result<()> {
        match key.code {
            KeyCode::Esc | KeyCode::Char('q') => self.quit = true,
            _ => {}
        }
        Ok(())
    }

    fn on_mouse(&mut self, _mouse: MouseEvent) -> Result<bool> {
        Ok(false)
    }

    fn render(&mut self, frame: &mut Frame) {
        self.frames += 1;
        let n = self.frames;
        publish("frames", &n.into());

        let area = frame.area();
        let chunks = Layout::vertical([
            Constraint::Length(3),
            Constraint::Min(1),
            Constraint::Length(1),
        ])
        .split(area);

        frame.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled("crow", Style::new().fg(Color::Rgb(0xc0, 0x84, 0xfc)).bold()),
                Span::styled(" — web runtime", Style::new().fg(Color::DarkGray)),
            ]))
            .block(Block::bordered().title(" gpu paint ")),
            chunks[0],
        );

        let body = Paragraph::new(vec![
            Line::from(Span::styled(
                "ratatui over wgpu over WebGL2",
                Style::new().fg(Color::Green),
            )),
            Line::from("the quick brown fox jumps over the lazy dog"),
            Line::from(Span::styled(
                "0123456789 !@#$%^&*() {}[] <>|/\\ ~`",
                Style::new().fg(Color::Yellow),
            )),
            Line::from(Span::styled(
                "unicode: — · ↑ ↓ ► ● ✓ 中文",
                Style::new().fg(Color::Cyan),
            )),
            Line::from(format!("frame {n}")),
        ])
        .block(Block::bordered().title(" glyphs "));
        frame.render_widget(body, chunks[1]);

        frame.render_widget(
            Paragraph::new(format!("frames={n}")).style(Style::new().fg(Color::DarkGray)),
            chunks[2],
        );
    }

    /// Repaint every tick: the frame counter is the harness's liveness signal.
    fn tick(&mut self) -> Result<bool> {
        Ok(true)
    }

    fn should_quit(&self) -> bool {
        self.quit
    }

    fn resize(&mut self, cols: u16, rows: u16) {
        publish("cols", &cols.into());
        publish("rows", &rows.into());
    }

    fn on_close(&mut self) {}
}

fn main() -> Result<()> {
    console_error_panic_hook::set_once();
    console_log::init_with_level(log::Level::Info).ok();
    publish("stage", &"main".into());

    let config = GuiConfig {
        title: "crow — web runtime".into(),
        ..GuiConfig::default()
    };

    // Returns as soon as winit has the runner: on the web the browser owns the
    // loop and drives us from requestAnimationFrame.
    crow_gui::run(config, |cols, rows| Ok(ProbeApp::new(cols, rows)))
}

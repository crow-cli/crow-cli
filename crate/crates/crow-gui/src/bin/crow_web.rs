//! Throwaway probe: does ratatui-wgpu actually paint into headless Chromium?
//!
//! Modelled on ratatui-wgpu's upstream `examples/web/hello_web.rs`. Renders a
//! bordered, coloured, text-bearing ratatui frame into a WebGL2 canvas and
//! publishes `window.__crowProbe` so a Playwright test can assert on it
//! deterministically instead of sleeping.

use std::cell::RefCell;
use std::num::NonZeroU32;
use std::rc::Rc;

use ratatui::prelude::*;
use ratatui::widgets::*;
use ratatui_wgpu::{Builder, Dimensions, Font, WgpuBackend};
use web_sys::HtmlCanvasElement;
use winit::application::ApplicationHandler;
use winit::event::WindowEvent;
use winit::event_loop::EventLoop;
// winit 0.30.13 names these `*WebSys` (upstream's hello_web example predates the rename).
use winit::platform::web::{EventLoopExtWebSys as _, WindowExtWebSys as _};
use winit::window::{Window, WindowAttributes};

const FONT: &[u8] = crow_gui::FONT_DATA;

/// Publish a value on `window.__crowProbe[key]` for the test harness to read.
fn publish(key: &str, value: &wasm_bindgen::JsValue) {
    if let Some(win) = web_sys::window() {
        let holder = js_sys::Reflect::get(&win, &"__crowProbe".into()).ok();
        let holder = match holder {
            Some(h) if h.is_object() => h,
            _ => {
                let obj = js_sys::Object::new();
                let _ = js_sys::Reflect::set(&win, &"__crowProbe".into(), &obj);
                obj.into()
            }
        };
        let _ = js_sys::Reflect::set(&holder, &key.into(), value);
    }
}

pub struct App {
    window: Rc<RefCell<Option<Window>>>,
    backend: Rc<RefCell<Option<Terminal<WgpuBackend<'static, 'static>>>>>,
    frames: Rc<RefCell<u32>>,
}

fn main() -> anyhow::Result<()> {
    console_error_panic_hook::set_once();
    console_log::init_with_level(log::Level::Info).unwrap();

    publish("stage", &"main".into());

    let event_loop = EventLoop::builder().build()?;
    let app = App {
        window: Rc::default(),
        backend: Rc::default(),
        frames: Rc::new(RefCell::new(0)),
    };
    // `spawn_app`, not `run_app`: on the web the browser owns the event loop,
    // so this returns immediately and winit drives us from requestAnimationFrame.
    event_loop.spawn_app(app);
    Ok(())
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &winit::event_loop::ActiveEventLoop) {
        publish("stage", &"resumed".into());

        let window = event_loop
            .create_window(WindowAttributes::default().with_title("crow wasm probe"))
            .expect("create window");
        *self.window.borrow_mut() = Some(window);

        let window = self.window.clone();
        let backend = self.backend.clone();

        wasm_bindgen_futures::spawn_local(async move {
            // Attach winit's canvas to the DOM and stretch it over the viewport.
            let (width, height) = {
                let win = window.borrow();
                let win = win.as_ref().expect("window");
                let canvas: HtmlCanvasElement = win.canvas().expect("canvas");
                let style = canvas.style();
                for (k, v) in [
                    ("display", "block"),
                    ("width", "100%"),
                    ("height", "100%"),
                    ("position", "absolute"),
                    ("top", "0"),
                    ("left", "0"),
                    ("z-index", "1"),
                ] {
                    let _ = style.set_property(k, v);
                }
                let doc = web_sys::window()
                    .and_then(|w| w.document())
                    .expect("document");
                let host = doc.get_element_by_id("glcanvas").expect("#glcanvas");
                host.append_with_node_1(&web_sys::Element::from(canvas.clone()))
                    .expect("append canvas");
                let bounds = canvas.get_bounding_client_rect();
                (
                    NonZeroU32::new(bounds.width() as u32).unwrap_or(NonZeroU32::MIN),
                    NonZeroU32::new(bounds.height() as u32).unwrap_or(NonZeroU32::MIN),
                )
            };

            publish("stage", &"building-backend".into());

            let canvas = window
                .borrow()
                .as_ref()
                .expect("window")
                .canvas()
                .expect("canvas");

            // Headless Chromium *does* expose `navigator.gpu` (127.0.0.1 is a secure
            // context) but `requestAdapter()` returns null — there is no WebGPU
            // adapter. `Backends::default()` is `all()`, so wgpu would pick the
            // WebGPU dispatch and fail with a misleading "gl support not compiled
            // in". Requesting GL only routes to wgpu-core's glow backend over
            // WebGL2 (ANGLE -> SwiftShader under headless).
            let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor {
                backends: wgpu::Backends::GL,
                ..Default::default()
            });

            let built = Builder::from_font(Font::new(FONT).expect("font"))
                .with_instance(instance)
                .with_width_and_height(Dimensions { width, height })
                .with_bg_color(Color::Rgb(0x1e, 0x1e, 0x2e))
                .with_fg_color(Color::Rgb(0xe0, 0xe0, 0xe0))
                // On the web the surface is a DOM canvas, not a native window.
                .build_with_target(wgpu::SurfaceTarget::Canvas(canvas))
                .await;

            match built {
                Ok(b) => {
                    *backend.borrow_mut() = Some(Terminal::new(b).expect("terminal"));
                    publish("stage", &"ready".into());
                    publish("ready", &true.into());
                }
                Err(e) => {
                    log::error!("backend build failed: {e:#}");
                    publish("stage", &"error".into());
                    publish("error", &format!("{e:#}").into());
                }
            }
        });
    }

    fn window_event(
        &mut self,
        _event_loop: &winit::event_loop::ActiveEventLoop,
        _window_id: winit::window::WindowId,
        event: WindowEvent,
    ) {
        if let WindowEvent::Resized(size) = event {
            if let Some(t) = self.backend.borrow_mut().as_mut() {
                t.backend_mut().resize(size.width, size.height);
            }
        }

        let mut frames = self.frames.borrow_mut();
        *frames += 1;
        let n = *frames;
        drop(frames);

        // Hold the RefCell guard in a binding: `borrow_mut().as_mut()` would drop
        // the temporary guard at the end of the `let ... else` statement.
        let mut guard = self.backend.borrow_mut();
        let Some(terminal) = guard.as_mut() else {
            return;
        };

        let _ = terminal.draw(|f| {
            let area = f.area();
            let chunks = Layout::vertical([
                Constraint::Length(3),
                Constraint::Min(1),
                Constraint::Length(1),
            ])
            .split(area);

            f.render_widget(
                Paragraph::new(Line::from(vec![
                    Span::styled("crow", Style::new().fg(Color::Rgb(0xc0, 0x84, 0xfc)).bold()),
                    Span::styled(" — wasm probe", Style::new().fg(Color::DarkGray)),
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
            f.render_widget(body, chunks[1]);

            f.render_widget(
                Paragraph::new(format!("frames={n}")).style(Style::new().fg(Color::DarkGray)),
                chunks[2],
            );
        });

        publish("frames", &(*self.frames.borrow()).into());

        if let Some(win) = self.window.borrow().as_ref() {
            win.request_redraw();
        }
    }
}

//! The winit + wgpu runner: one event-loop body, two ways to get a surface.
//!
//! Lifted from fresh-gui (`crates/fresh-gui/src/lib.rs:245-656`) — the blueprint
//! for this crate — minus its native menu bar / macOS / Windows platform
//! modules, which crow does not have. The event handling (`window_event`,
//! `about_to_wait`) is a single body compiled for both runtimes; the only
//! cfg-split is *how the state comes to exist*, which lives in [`crate::slots`].

use std::num::NonZeroU32;
use std::time::Duration;

use anyhow::{Context, Result};
use ratatui::backend::Backend;
use ratatui::Terminal;
use ratatui_wgpu::{Builder, Dimensions, Font, WgpuBackend};
use winit::application::ApplicationHandler;
use winit::event::{ElementState, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::keyboard::KeyLocation;
use winit::window::{WindowAttributes, WindowId};

use crate::event::{KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use crate::input::{pixel_to_cell, translate_key_event, translate_modifiers, translate_mouse_button};
use crate::slots::{StateSlot, WindowHandle};
use crate::{GuiApplication, GuiConfig, FONT_DATA};

// `ControlFlow::WaitUntil` carries `std::time::Instant` on every platform except
// winit's web one, where it carries `web_time::Instant` (winit gates that on
// `all(target_family = "wasm", not(target_os = "wasi"))`, and std's Instant is
// not implemented for wasm32-unknown-unknown anyway).
#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;
#[cfg(target_arch = "wasm32")]
use web_time::Instant;

#[cfg(not(target_arch = "wasm32"))]
use std::sync::Arc;
#[cfg(target_arch = "wasm32")]
use winit::window::Window;

/// Frame duration target (60fps).
const FRAME_DURATION: Duration = Duration::from_millis(16);

/// Factory for the hosted application, called once the backend is up with the
/// initial grid size `(cols, rows)`.
pub(crate) type CreateAppFn<A> = Box<dyn FnOnce(u16, u16) -> Result<A>>;

/// Run the GUI event loop, hosting whatever `create_app` returns.
///
/// Native this blocks until the window closes. On the web the browser owns the
/// loop, so `spawn_app` hands the runner to winit and returns immediately —
/// `Ok(())` there means "launched", not "finished".
pub fn run<F, A>(config: GuiConfig, create_app: F) -> Result<()>
where
    F: FnOnce(u16, u16) -> Result<A> + 'static,
    A: GuiApplication + 'static,
{
    #[cfg(not(target_arch = "wasm32"))]
    let event_loop = EventLoop::new().context("failed to create winit event loop")?;
    #[cfg(target_arch = "wasm32")]
    let event_loop = EventLoop::builder()
        .build()
        .context("failed to create winit event loop")?;

    // WaitUntil, not Poll: Poll makes winit re-arm immediately, spinning the run
    // loop at 100% CPU for the same ~60fps. WaitUntil is also what winit's web
    // platform turns into a scheduler/setTimeout wake-up, so one pacing policy
    // covers both runtimes.
    event_loop.set_control_flow(ControlFlow::WaitUntil(Instant::now() + FRAME_DURATION));

    // `mut` only matters natively, where `run_app` borrows the runner; on the web
    // `spawn_app` takes it by value and winit drives it from the browser loop.
    #[cfg_attr(target_arch = "wasm32", allow(unused_mut))]
    let mut runner = WgpuRunner {
        config,
        create_app: Some(Box::new(create_app)),
        state: StateSlot::empty(),
    };

    #[cfg(not(target_arch = "wasm32"))]
    event_loop
        .run_app(&mut runner)
        .context("winit event loop error")?;

    #[cfg(target_arch = "wasm32")]
    {
        use winit::platform::web::EventLoopExtWebSys as _;
        event_loop.spawn_app(runner);
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Runner state
// ---------------------------------------------------------------------------

/// Everything the event loop needs once the backend exists.
pub(crate) struct RunnerState<A: GuiApplication> {
    pub app: A,
    pub terminal: Terminal<WgpuBackend<'static, 'static>>,
    pub window: WindowHandle,
    pub needs_render: bool,
    pub last_render: Instant,
    /// Cursor position in pixels, tracked across `CursorMoved` events.
    pub cursor_position: (f64, f64),
    /// Modifier state, tracked across `ModifiersChanged` events.
    pub modifiers: KeyModifiers,
    /// Which mouse button is held, for drag detection.
    pub pressed_button: Option<MouseButton>,
    /// Cell size in pixels (width, height), for pixel-to-cell conversion.
    pub cell_size: (f64, f64),
    /// Which Alt/Option key is held (macOS left/right distinction).
    pub alt_location: Option<KeyLocation>,
}

impl<A: GuiApplication> RunnerState<A> {
    fn new(
        app: A,
        terminal: Terminal<WgpuBackend<'static, 'static>>,
        window: WindowHandle,
        cell_size: (f64, f64),
    ) -> Self {
        Self {
            app,
            terminal,
            window,
            needs_render: true,
            last_render: Instant::now(),
            cursor_position: (0.0, 0.0),
            modifiers: KeyModifiers::NONE,
            pressed_button: None,
            cell_size,
            alt_location: None,
        }
    }
}

/// Winit application bridging winit/wgpu to [`GuiApplication`].
pub(crate) struct WgpuRunner<A: GuiApplication> {
    config: GuiConfig,
    /// Factory called once the window and backend are ready.
    create_app: Option<CreateAppFn<A>>,
    state: StateSlot<A>,
}

impl<A: GuiApplication + 'static> ApplicationHandler for WgpuRunner<A> {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        #[cfg(not(target_arch = "wasm32"))]
        self.resumed_native(event_loop);
        #[cfg(target_arch = "wasm32")]
        self.resumed_web(event_loop);
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        self.state.with_mut(|state| match event {
            WindowEvent::CloseRequested => {
                state.app.on_close();
                event_loop.exit();
            }

            WindowEvent::Resized(size) => {
                if size.width > 0 && size.height > 0 {
                    state.terminal.backend_mut().resize(size.width, size.height);
                    // Re-derive the cell size: the grid may have changed.
                    if let Ok(ws) = state.terminal.backend_mut().window_size() {
                        let cols = ws.columns_rows.width;
                        let rows = ws.columns_rows.height;
                        state.cell_size = (
                            ws.pixels.width as f64 / cols.max(1) as f64,
                            ws.pixels.height as f64 / rows.max(1) as f64,
                        );
                        state.app.resize(cols, rows);
                    }
                    state.needs_render = true;
                }
            }

            WindowEvent::ModifiersChanged(mods) => {
                state.modifiers = translate_modifiers(&mods.state());
            }

            WindowEvent::KeyboardInput { event, .. } => {
                // Track the Alt location before dropping releases.
                if let winit::keyboard::Key::Named(winit::keyboard::NamedKey::Alt) =
                    &event.logical_key
                {
                    match event.state {
                        ElementState::Pressed => state.alt_location = Some(event.location),
                        ElementState::Released => state.alt_location = None,
                    }
                }

                if event.state == ElementState::Released {
                    return;
                }
                if let Some(key_event) =
                    translate_key_event(&event, state.modifiers, state.alt_location)
                {
                    if let Err(e) = state.app.on_key(key_event) {
                        log::error!("key handling error: {e}");
                    }
                    state.needs_render = true;
                }
            }

            WindowEvent::MouseInput {
                state: btn_state,
                button,
                ..
            } => {
                if let Some(ct_btn) = translate_mouse_button(button) {
                    let kind = match btn_state {
                        ElementState::Pressed => {
                            state.pressed_button = Some(ct_btn);
                            MouseEventKind::Down(ct_btn)
                        }
                        ElementState::Released => {
                            state.pressed_button = None;
                            MouseEventKind::Up(ct_btn)
                        }
                    };
                    dispatch_mouse(state, kind);
                }
            }

            WindowEvent::CursorMoved { position, .. } => {
                state.cursor_position = (position.x, position.y);
                let kind = match state.pressed_button {
                    Some(btn) => MouseEventKind::Drag(btn),
                    None => MouseEventKind::Moved,
                };
                dispatch_mouse(state, kind);
            }

            WindowEvent::MouseWheel { delta, .. } => {
                let (h_lines, v_lines) = match delta {
                    MouseScrollDelta::LineDelta(h, v) => (h as i32, v as i32),
                    MouseScrollDelta::PixelDelta(pos) => {
                        let line_h = state.cell_size.1.max(1.0);
                        ((pos.x / line_h) as i32, (pos.y / line_h) as i32)
                    }
                };
                for _ in 0..v_lines.unsigned_abs() {
                    let kind = if v_lines > 0 {
                        MouseEventKind::ScrollUp
                    } else {
                        MouseEventKind::ScrollDown
                    };
                    dispatch_mouse(state, kind);
                }

                for _ in 0..h_lines.unsigned_abs() {
                    let kind = if h_lines > 0 {
                        MouseEventKind::ScrollRight
                    } else {
                        MouseEventKind::ScrollLeft
                    };
                    dispatch_mouse(state, kind);
                }
            }

            WindowEvent::RedrawRequested => {
                if state.needs_render && state.last_render.elapsed() >= FRAME_DURATION {
                    if let Err(e) = state.terminal.draw(|frame| state.app.render(frame)) {
                        log::error!("render error: {e}");
                    }
                    state.last_render = Instant::now();
                    state.needs_render = false;
                }
            }

            _ => {}
        });
    }

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        // Pace the loop at ~60fps even when nothing is dirty: the app's `tick`
        // is what notices that the world moved (bus events, blinking cursor).
        event_loop.set_control_flow(ControlFlow::WaitUntil(Instant::now() + FRAME_DURATION));

        let mut quit = false;
        self.state.with_mut(|state| {
            match state.app.tick() {
                Ok(true) => state.needs_render = true,
                Ok(false) => {}
                Err(e) => log::error!("tick error: {e}"),
            }

            // A theme switch shows up as a new ANSI color table.
            if let Some(table) = state.app.take_color_update() {
                state.terminal.backend_mut().update_color_table(table);
                state.needs_render = true;
            }

            if state.app.should_quit() {
                state.app.on_close();
                quit = true;
            }

            if state.needs_render {
                state.window.request_redraw();
            }
        });

        if quit {
            event_loop.exit();
        }
    }
}

/// Turn a mouse kind into a cell-coordinate event, hand it to the app, and
/// remember whether it wants a re-render.
fn dispatch_mouse<A: GuiApplication>(state: &mut RunnerState<A>, kind: MouseEventKind) {
    let (column, row) = pixel_to_cell(state.cursor_position, state.cell_size);
    let event = MouseEvent {
        kind,
        column,
        row,
        modifiers: state.modifiers,
    };
    match state.app.on_mouse(event) {
        Ok(true) => state.needs_render = true,
        Ok(false) => {}
        Err(e) => log::error!("mouse handling error: {e}"),
    }
}

// ---------------------------------------------------------------------------
// Backend construction — shared helpers
// ---------------------------------------------------------------------------

/// `NonZeroU32` that never panics: a zero-sized surface becomes 1x1 and the
/// next `Resized` event fixes it.
fn nz(v: u32) -> NonZeroU32 {
    NonZeroU32::new(v).unwrap_or(NonZeroU32::MIN)
}

/// The runtime-independent half of backend construction: embedded font, size,
/// reset colors, optional ANSI color table.
fn styled_builder(config: &GuiConfig, dims: Dimensions) -> Result<Builder<'static>> {
    let font = Font::new(FONT_DATA).context("failed to load embedded font")?;
    let mut builder = Builder::from_font(font)
        .with_width_and_height(dims)
        .with_bg_color(config.reset_bg)
        .with_fg_color(config.reset_fg);
    if let Some(table) = config.color_table.clone() {
        builder = builder.with_color_table(table);
    }
    Ok(builder)
}

/// Derive the grid `(cols, rows)` and one cell's pixel size from a live backend.
fn grid_and_cell(
    terminal: &mut Terminal<WgpuBackend<'static, 'static>>,
) -> Result<(u16, u16, (f64, f64))> {
    let ws = terminal
        .backend_mut()
        .window_size()
        .context("failed to query window size from backend")?;
    let cols = ws.columns_rows.width;
    let rows = ws.columns_rows.height;
    let cell_size = (
        ws.pixels.width as f64 / cols.max(1) as f64,
        ws.pixels.height as f64 / rows.max(1) as f64,
    );
    Ok((cols, rows, cell_size))
}

// ---------------------------------------------------------------------------
// Native runtime: the backend is built synchronously inside `resumed`
// ---------------------------------------------------------------------------

#[cfg(not(target_arch = "wasm32"))]
impl<A: GuiApplication + 'static> WgpuRunner<A> {
    fn resumed_native(&mut self, event_loop: &ActiveEventLoop) {
        if self.state.exists() {
            return; // already initialized
        }
        match self.create_state(event_loop) {
            Ok(state) => {
                state.window.request_redraw();
                self.state.install(state);
            }
            Err(e) => {
                log::error!("failed to initialize GUI: {e:#}");
                event_loop.exit();
            }
        }
    }

    fn create_state(&mut self, event_loop: &ActiveEventLoop) -> Result<RunnerState<A>> {
        let mut attrs = WindowAttributes::default()
            .with_title(&self.config.title)
            .with_inner_size(winit::dpi::PhysicalSize::new(
                self.config.width,
                self.config.height,
            ));
        // Wayland app_id + X11 WM_CLASS, so the desktop entry's StartupWMClass
        // can group the window. Fully qualified: both platform traits define
        // `with_name`, and the backend that isn't running ignores its field.
        #[cfg(target_os = "linux")]
        {
            attrs = winit::platform::wayland::WindowAttributesExtWayland::with_name(
                attrs,
                self.config.app_id.clone(),
                self.config.app_id.clone(),
            );
            attrs = winit::platform::x11::WindowAttributesExtX11::with_name(
                attrs,
                self.config.app_id.clone(),
                self.config.app_id.clone(),
            );
        }
        let window: WindowHandle =
            Arc::new(event_loop.create_window(attrs).context("failed to create window")?);
        let size = window.inner_size();

        let builder = styled_builder(
            &self.config,
            Dimensions {
                width: nz(size.width),
                height: nz(size.height),
            },
        )?;
        // Adapter + device requests are async; native has a thread to block on.
        let backend = futures_lite::future::block_on(builder.build_with_target(window.clone()))
            .context("failed to create wgpu backend")?;

        let mut terminal = Terminal::new(backend).context("failed to create ratatui terminal")?;
        let (cols, rows, cell_size) = grid_and_cell(&mut terminal)?;

        let create_app = self
            .create_app
            .take()
            .context("create_app already consumed")?;
        let app = create_app(cols, rows)?;

        Ok(RunnerState::new(app, terminal, window, cell_size))
    }
}

// ---------------------------------------------------------------------------
// Web runtime: the backend arrives from a future, so the state slot is shared
// ---------------------------------------------------------------------------

#[cfg(target_arch = "wasm32")]
impl<A: GuiApplication + 'static> WgpuRunner<A> {
    fn resumed_web(&mut self, event_loop: &ActiveEventLoop) {
        if self.state.exists() {
            return; // already initialized
        }
        let Some(create_app) = self.create_app.take() else {
            log::error!("create_app already consumed");
            return;
        };

        let attrs = WindowAttributes::default().with_title(&self.config.title);
        let window = match event_loop.create_window(attrs) {
            Ok(window) => window,
            Err(e) => {
                log::error!("failed to create window: {e:#}");
                event_loop.exit();
                return;
            }
        };

        let config = self.config.clone();
        let slot = self.state.clone();
        wasm_bindgen_futures::spawn_local(async move {
            match build_web_state(window, &config, create_app).await {
                Ok(state) => {
                    state.window.request_redraw();
                    slot.install(state);
                }
                Err(e) => log::error!("failed to initialize GUI: {e:#}"),
            }
        });
    }
}

/// Build the browser-side state: attach the canvas, then request the GL
/// adapter and the backend that paints into it.
#[cfg(target_arch = "wasm32")]
async fn build_web_state<A: GuiApplication + 'static>(
    window: Window,
    config: &GuiConfig,
    create_app: CreateAppFn<A>,
) -> Result<RunnerState<A>> {
    use winit::platform::web::WindowExtWebSys as _;

    let canvas: web_sys::HtmlCanvasElement = window
        .canvas()
        .context("winit window has no canvas")?;
    let dims = attach_canvas(&canvas)?;

    // winit listens for keydown/keyup on the canvas itself (it sets
    // `tabindex="0"`), so a canvas that never receives DOM focus is a deaf
    // terminal. Focus must happen after the append: `focus()` on a detached
    // element is a no-op.
    window.focus_window();

    // Headless Chromium *does* expose `navigator.gpu` (127.0.0.1 is a secure
    // context) but `requestAdapter()` returns null — there is no WebGPU adapter.
    // `Backends::default()` is `all()`, so wgpu picks the WebGPU dispatch and
    // fails with a misleading "gl support not compiled in" (the WebGPU backend
    // hardcodes its `supported_backends`). Asking for GL only routes to
    // wgpu-core's glow backend over WebGL2 (ANGLE -> SwiftShader headless).
    let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor {
        backends: wgpu::Backends::GL,
        ..Default::default()
    });

    let backend = styled_builder(config, dims)?
        .with_instance(instance)
        // On the web the surface is a DOM canvas, not a native window.
        .build_with_target(wgpu::SurfaceTarget::Canvas(canvas))
        .await
        .context("failed to create wgpu backend")?;

    let mut terminal = Terminal::new(backend).context("failed to create ratatui terminal")?;
    let (cols, rows, cell_size) = grid_and_cell(&mut terminal)?;
    let app = create_app(cols, rows)?;

    Ok(RunnerState::new(app, terminal, window, cell_size))
}

/// Append winit's canvas to the page's `#glcanvas` host and stretch it over the
/// viewport, then report the size it ended up with.
#[cfg(target_arch = "wasm32")]
fn attach_canvas(canvas: &web_sys::HtmlCanvasElement) -> Result<Dimensions> {
    let style = canvas.style();
    for (key, value) in [
        ("display", "block"),
        ("width", "100%"),
        ("height", "100%"),
        ("position", "absolute"),
        ("top", "0"),
        ("left", "0"),
        ("z-index", "1"),
    ] {
        style
            .set_property(key, value)
            .map_err(|e| anyhow::anyhow!("canvas style {key}: {e:?}"))?;
    }

    let document = web_sys::window()
        .and_then(|w| w.document())
        .context("no document")?;
    let host = document
        .get_element_by_id("glcanvas")
        .context("no #glcanvas host element in the page")?;
    host.append_with_node_1(&web_sys::Element::from(canvas.clone()))
        .map_err(|e| anyhow::anyhow!("append canvas: {e:?}"))?;

    let bounds = canvas.get_bounding_client_rect();
    Ok(Dimensions {
        width: nz(bounds.width() as u32),
        height: nz(bounds.height() as u32),
    })
}

//! crow-gui — the runtime-agnostic ratatui-over-wgpu UI service.
//!
//! One rendering core, two runtimes:
//!
//! * `--web`  — this crate's `crow-web` bin, compiled to wasm; the surface is a
//!   DOM canvas and the event loop is the browser's. Verified headlessly with
//!   Playwright (see `web/` and `scripts/build-web.sh`).
//! * `--gui`  — a native winit window in the `crow` binary; same runner, same
//!   frames, different surface target.
//!
//! The crate deliberately knows nothing about crow's `App`: it hosts anything
//! implementing [`GuiApplication`], exactly as fresh-gui hosts fresh-editor
//! (whose runner this is lifted from). The two runtimes differ in exactly one
//! place — how the wgpu backend comes to exist — and that difference is
//! isolated in [`slots`]; the event loop itself is one body.
//!
//! Input arrives as [`event`] types (crossterm-shaped, because crossterm itself
//! does not compile for wasm32) translated from winit by [`input`].

use ratatui::style::Color;

pub mod event;
pub mod input;
mod runner;
mod slots;

pub use ratatui_wgpu::ColorTable;
pub use runner::run;

use crate::event::{KeyEvent, MouseEvent};

/// Embedded Cascadia Mono (SIL Open Font License 1.1, see
/// `fonts/CascadiaOFL.txt`). Shared by every runtime so the native window and
/// the browser canvas measure text identically.
pub const FONT_DATA: &[u8] = include_bytes!("../fonts/CascadiaMono-Regular.ttf");

// ---------------------------------------------------------------------------
// Public trait — implemented by the hosted application
// ---------------------------------------------------------------------------

/// An application that can be hosted in a GPU window.
///
/// Input is delivered as terminal-shaped events so the same handling code works
/// in a terminal frontend and in a window; `render` is a plain ratatui draw.
pub trait GuiApplication {
    /// Handle a translated key event.
    fn on_key(&mut self, key: KeyEvent) -> anyhow::Result<()>;

    /// Handle a mouse event. Returns `true` if a re-render is needed.
    fn on_mouse(&mut self, mouse: MouseEvent) -> anyhow::Result<bool>;

    /// Render the application into a ratatui frame.
    fn render(&mut self, frame: &mut ratatui::Frame);

    /// Per-tick housekeeping, called ~60x/second whether or not anything
    /// happened. Returns `true` if a re-render is needed.
    ///
    /// This is where a hosted app drains its event bus: the loop is the only
    /// thing that wakes on a timer, so an app that never returns `true` here
    /// only repaints on input.
    fn tick(&mut self) -> anyhow::Result<bool>;

    /// Whether the application wants to quit.
    fn should_quit(&self) -> bool;

    /// Handle a grid resize to `(cols, rows)`.
    fn resize(&mut self, cols: u16, rows: u16);

    /// Called when the window is about to close (e.g. to save state).
    fn on_close(&mut self);

    /// Return an updated ANSI color table if the theme changed since the last
    /// call. Polled every tick; `Some(table)` updates the wgpu backend so named
    /// colors match the theme.
    fn take_color_update(&mut self) -> Option<ColorTable> {
        None
    }
}

// ---------------------------------------------------------------------------
// Window configuration
// ---------------------------------------------------------------------------

/// Configuration for the window and its backend.
#[derive(Clone, Debug)]
pub struct GuiConfig {
    /// Window title.
    pub title: String,
    /// Initial window width in pixels (native; the browser sizes the canvas).
    pub width: u32,
    /// Initial window height in pixels (native; the browser sizes the canvas).
    pub height: u32,
    /// Background color used where a cell says `Color::Reset`.
    pub reset_bg: Color,
    /// Foreground color used where a cell says `Color::Reset`.
    pub reset_fg: Color,
    /// ANSI base-16 color table. `None` uses the ratatui-wgpu defaults.
    pub color_table: Option<ColorTable>,
    /// Wayland app id / X11 WM_CLASS (`with_name`). The desktop entry's
    /// `StartupWMClass` must match this or the launcher cannot group windows.
    pub app_id: String,
}

impl Default for GuiConfig {
    fn default() -> Self {
        Self {
            title: "crow".into(),
            width: 1280,
            height: 800,
            reset_bg: Color::Rgb(0x1e, 0x1e, 0x2e),
            reset_fg: Color::Rgb(0xe0, 0xe0, 0xe0),
            color_table: None,
            app_id: "crow".into(),
        }
    }
}

/// ANSI color table tuned for dark backgrounds (bg ~#1e1e1e): standard colors
/// brightened, light variants vivid.
pub fn dark_color_table() -> ColorTable {
    ColorTable {
        BLACK: [0, 0, 0],
        RED: [204, 60, 60],
        GREEN: [80, 180, 80],
        YELLOW: [220, 180, 60],
        BLUE: [70, 130, 230],
        MAGENTA: [190, 90, 220],
        CYAN: [60, 190, 190],
        GRAY: [160, 160, 160],
        DARKGRAY: [100, 100, 100],
        LIGHTRED: [240, 110, 110],
        LIGHTGREEN: [130, 220, 130],
        LIGHTYELLOW: [240, 220, 130],
        LIGHTBLUE: [130, 170, 255],
        LIGHTMAGENTA: [220, 140, 255],
        LIGHTCYAN: [120, 230, 230],
        WHITE: [230, 230, 230],
    }
}

/// ANSI color table tuned for light backgrounds (bg ~#ffffff): colors darkened
/// and saturated so they stay readable on white.
pub fn light_color_table() -> ColorTable {
    ColorTable {
        BLACK: [0, 0, 0],
        RED: [180, 0, 0],
        GREEN: [0, 130, 0],
        YELLOW: [150, 120, 0],
        BLUE: [0, 50, 180],
        MAGENTA: [140, 0, 140],
        CYAN: [0, 130, 130],
        GRAY: [130, 130, 130],
        DARKGRAY: [80, 80, 80],
        LIGHTRED: [210, 60, 60],
        LIGHTGREEN: [40, 160, 40],
        LIGHTYELLOW: [180, 150, 0],
        LIGHTBLUE: [50, 90, 210],
        LIGHTMAGENTA: [170, 50, 170],
        LIGHTCYAN: [0, 160, 160],
        WHITE: [255, 255, 255],
    }
}

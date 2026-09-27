//! The native `--gui` runtime: crow in its own GPU-painted window.
//!
//! Everything window- and GPU-shaped lives in `crow-gui`, the UI service this
//! shares with the `--web` wasm runtime. This module is only the thin native
//! half of that split: it turns the startup pieces `main()` builds (Phase 3.3)
//! into a [`CrowApp`] and hands them to the runner.

pub(crate) mod app;

use anyhow::Result;
use crow_gui::GuiConfig;

use crate::Startup;

pub(crate) use app::CrowApp;

/// Open the native window and block until it closes, hosting crow's `App`.
pub(crate) fn run_crow_app(start: Startup) -> Result<()> {
    let Startup { app, controller, bus_rx, .. } = start;
    let mut app = app;
    // The window has no kitty-graphics channel: the pet and backdrop must stay
    // on the half-block art path `ui::draw` paints, never escape sequences
    // (TODO "Kitty graphics", verify `pet_pixels` stays false).
    app.pet_pixels = false;
    // Seed the backend from the startup theme: `Color::Reset` cells and the
    // ANSI base-16 names match the palette the TTY would have shown. Mode
    // flips after that travel through `CrowApp::take_color_update`.
    let cfg = GuiConfig {
        reset_bg: app.theme.bg,
        reset_fg: app.theme.fg,
        color_table: Some(CrowApp::table_for(app.theme.mode)),
        ..GuiConfig::default()
    };
    crow_gui::run(cfg, move |_cols, _rows| {
        Ok(CrowApp::new(app, controller, bus_rx))
    })
}

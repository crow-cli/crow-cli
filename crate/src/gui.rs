//! The native `--gui` runtime: crow in its own GPU-painted window.
//!
//! Everything window- and GPU-shaped lives in `crow-gui`, the UI service this
//! shares with the `--web` wasm runtime. This module is only the thin native
//! half of that split: a [`GuiConfig`] and a [`GuiApplication`].
//!
//! Phase 1.3: the window opens, ratatui paints into it, keys reach the app and
//! closing exits 0. The hosted application is still a placeholder — Phase 3.1
//! swaps in the `CrowApp` adapter over `App`/`Controller`/`ui::draw`.

use anyhow::Result;
use crow_gui::event::{KeyCode, KeyEvent, KeyEventKind, MouseEvent};
use crow_gui::{GuiApplication, GuiConfig};
use ratatui::prelude::*;
use ratatui::widgets::{Block, Paragraph};

/// Open the native window and block until it closes.
pub(crate) fn run_window() -> Result<()> {
    crow_gui::run(GuiConfig::default(), |cols, rows| {
        Ok(PlaceholderApp::new(cols, rows))
    })
}

/// Phase 1.3's stand-in for crow's `App`: paints one bordered frame over the
/// config's background and quits on Esc or q.
pub(crate) struct PlaceholderApp {
    cols: u16,
    rows: u16,
    quit: bool,
}

impl PlaceholderApp {
    pub(crate) fn new(cols: u16, rows: u16) -> Self {
        Self { cols, rows, quit: false }
    }
}

impl GuiApplication for PlaceholderApp {
    fn on_key(&mut self, key: KeyEvent) -> Result<()> {
        // winit reports Press, Repeat and Release; act once, on the press.
        if key.kind == KeyEventKind::Press && matches!(key.code, KeyCode::Esc | KeyCode::Char('q')) {
            self.quit = true;
        }
        Ok(())
    }

    fn on_mouse(&mut self, _mouse: MouseEvent) -> Result<bool> {
        Ok(false)
    }

    fn render(&mut self, frame: &mut Frame) {
        let (cols, rows) = (self.cols, self.rows);
        frame.render_widget(
            Paragraph::new(vec![
                Line::from(vec![
                    Span::styled("crow", Style::new().fg(Color::Rgb(0xc0, 0x84, 0xfc)).bold()),
                    Span::styled(" — native GPU window", Style::new().fg(Color::DarkGray)),
                ]),
                Line::from(Span::styled(
                    "ratatui over wgpu, hosted by crow-gui's runner",
                    Style::new().fg(Color::Green),
                )),
                Line::from(format!("grid {cols}x{rows}")),
                Line::from(Span::styled("Esc or q to quit", Style::new().fg(Color::Yellow))),
            ])
            .block(Block::bordered().title(" phase 1.3 ")),
            frame.area(),
        );
    }

    /// Nothing animates yet, so repaint only on input and resize. Phase 3.2
    /// turns this into the event-bus drain that wakes the real app.
    fn tick(&mut self) -> Result<bool> {
        Ok(false)
    }

    fn should_quit(&self) -> bool {
        self.quit
    }

    fn resize(&mut self, cols: u16, rows: u16) {
        self.cols = cols;
        self.rows = rows;
    }

    fn on_close(&mut self) {
        // Phase 4.2: controller.send(Cmd::Shutdown) + flush the session id line.
    }
}

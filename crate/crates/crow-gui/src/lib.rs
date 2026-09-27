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
//! implementing the (W.3) `GuiApplication` trait, exactly as fresh-gui hosts
//! fresh-editor.

/// Embedded Cascadia Mono (SIL Open Font License 1.1, see
/// `fonts/CascadiaOFL.txt`). Shared by every runtime so the native window and
/// the browser canvas measure text identically.
pub const FONT_DATA: &[u8] = include_bytes!("../fonts/CascadiaMono-Regular.ttf");

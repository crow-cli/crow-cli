//! The textual-diff-view diff renderer, vendored from `diff-sandbox` at 100%
//! cell parity with the Python widget, plus the glue that turns an ACP
//! tool-call diff block into transcript lines.
//!
//! `layout`/`pipeline`/`sequencematcher`/`theme` are the parity-verified core:
//! a line-level matcher for the geometry, a char-level one per equal-sized
//! replace for the inline highlight, and a cell-exact port of Textual's
//! compose/wrap/clip arithmetic. `patch` walks a unified git patch back into
//! the two sides' lines, and `view` blits the rows into ratatui lines.
//!
//! The vendored core stays whole rather than being cut down to what the
//! transcript paints today: `layout` carries the split view and `theme` the
//! full palette beside the unified card crow renders. Keeping them
//! byte-identical to `diff-sandbox` is what makes the parity harness there
//! still say something about this copy, and the tests inside `layout` compile
//! and run the unused half, so it cannot rot silently. Hence the allow.
#![allow(dead_code)]

pub mod layout;
pub mod patch;
pub mod pipeline;
pub mod sequencematcher;
pub mod theme;
pub mod view;

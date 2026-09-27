//! The only place the two runtimes disagree: who owns the window and the state.
//!
//! Native builds the wgpu backend synchronously inside `resumed()`, so the
//! runner can own its state outright. The browser cannot: requesting an adapter
//! is a promise, so the state arrives later from a `spawn_local` future and the
//! slot has to be shared with that future. Everything downstream of the slot
//! (`window_event`, `about_to_wait`) is one body compiled for both.
//!
//! `target_arch = "wasm32"` is the right gate here: winit's web platform is
//! exactly `all(target_family = "wasm", target_os = "unknown")` (winit
//! build.rs:11) and it `compile_error!`s on every other wasm target.

use winit::window::Window;

use crate::runner::RunnerState;
use crate::GuiApplication;

/// Owned handle to the winit window.
///
/// Native is `Arc<Window>` because the wgpu surface is created from a clone
/// while the runner keeps driving events; on the web the surface comes from the
/// window's DOM canvas — a separate JS object — so the plain `Window` is enough.
#[cfg(not(target_arch = "wasm32"))]
pub(crate) type WindowHandle = std::sync::Arc<Window>;
#[cfg(target_arch = "wasm32")]
pub(crate) type WindowHandle = Window;

#[cfg(not(target_arch = "wasm32"))]
type Inner<A> = Option<RunnerState<A>>;
#[cfg(target_arch = "wasm32")]
type Inner<A> = std::rc::Rc<std::cell::RefCell<Option<RunnerState<A>>>>;

/// Where the runner keeps its [`RunnerState`].
pub(crate) struct StateSlot<A: GuiApplication> {
    inner: Inner<A>,
}

impl<A: GuiApplication + 'static> StateSlot<A> {
    /// An empty slot — the backend is not up yet.
    pub fn empty() -> Self {
        #[cfg(not(target_arch = "wasm32"))]
        {
            Self { inner: None }
        }
        #[cfg(target_arch = "wasm32")]
        {
            Self {
                inner: std::rc::Rc::new(std::cell::RefCell::new(None)),
            }
        }
    }

    /// Is the backend up (i.e. is there a state to drive)?
    pub fn exists(&self) -> bool {
        #[cfg(not(target_arch = "wasm32"))]
        {
            self.inner.is_some()
        }
        #[cfg(target_arch = "wasm32")]
        {
            self.inner.borrow().is_some()
        }
    }

    /// Run `f` against the live state, or nothing if the backend is not up.
    pub fn with_mut<R>(&mut self, f: impl FnOnce(&mut RunnerState<A>) -> R) -> Option<R> {
        #[cfg(not(target_arch = "wasm32"))]
        {
            self.inner.as_mut().map(f)
        }
        #[cfg(target_arch = "wasm32")]
        {
            self.inner.borrow_mut().as_mut().map(f)
        }
    }

    /// Native: install the state built in `resumed()`.
    #[cfg(not(target_arch = "wasm32"))]
    pub fn install(&mut self, state: RunnerState<A>) {
        self.inner = Some(state);
    }

    /// Web: install the state built by the backend future, through a `clone()`.
    #[cfg(target_arch = "wasm32")]
    pub fn install(&self, state: RunnerState<A>) {
        *self.inner.borrow_mut() = Some(state);
    }
}

/// The web runtime hands a second handle of the same slot to its backend
/// future; native never needs one.
#[cfg(target_arch = "wasm32")]
impl<A: GuiApplication + 'static> Clone for StateSlot<A> {
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
        }
    }
}

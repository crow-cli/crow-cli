//! ask_overlays: extracted verbatim from src/app.rs (Phase 1 split).

use crate::bus::{PermissionAskOption, PermissionAskReply};

/// Overlay for one ACP `session/request_permission` ask.
pub struct PermissionAskOverlay {
    pub title: String,
    pub sel: usize,
    pub options: Vec<PermissionAskOption>,
    pub(crate) reply: Option<tokio::sync::oneshot::Sender<PermissionAskReply>>,
}

/// One live ACP form elicitation. Its editor is separate from the composer.
pub struct ElicitationAskOverlay {
    pub form: crate::elicitation::ElicitationFormState,
    /// Scroll offset of the markdown description pane (render clamps it to
    /// the actual content height, so `usize::MAX` reliably reaches the end).
    pub scroll: usize,
    pub(crate) reply: Option<tokio::sync::oneshot::Sender<crate::elicitation::ElicitationReply>>,
}

impl Drop for ElicitationAskOverlay {
    fn drop(&mut self) {
        if let Some(reply) = self.reply.take() {
            let _ = reply.send(crate::elicitation::ElicitationReply::Cancelled);
        }
    }
}

impl Drop for PermissionAskOverlay {
    fn drop(&mut self) {
        if let Some(reply) = self.reply.take() {
            let _ = reply.send(PermissionAskReply::Cancelled);
        }
    }
}

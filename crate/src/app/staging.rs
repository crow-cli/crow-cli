//! staging: extracted verbatim from src/app.rs (Phase 1 split).

use super::*;
use crate::bus::SessionListItem;
use crate::locale::Locale;
use crate::transcript::{clamp_str, Transcript};

pub(crate) fn ui_session(event: &crate::events::UiEvent) -> Option<&str> {
    use crate::events::UiEvent;
    match event {
        UiEvent::SessionStatus { session, .. }
        | UiEvent::TurnStart { session, .. }
        | UiEvent::TurnEnd { session, .. }
        | UiEvent::TextDelta { session, .. }
        | UiEvent::ReasoningDelta { session, .. }
        | UiEvent::ToolCallPreparing { session }
        | UiEvent::AssistantFinal { session, .. }
        | UiEvent::ToolCall { session, .. }
        | UiEvent::ToolResult { session, .. }
        | UiEvent::Usage { session, .. }
        | UiEvent::ContextUsage { session, .. }
        | UiEvent::UserInjected { session, .. }
        | UiEvent::UserMessage { session, .. }
        | UiEvent::SessionTitle { session, .. }
        | UiEvent::SessionNotice { session, .. }
        | UiEvent::SessionModel { session, .. }
        | UiEvent::Plan { session, .. }
        | UiEvent::PlanMode { session, .. }
        | UiEvent::SandboxMode { session, .. }
        | UiEvent::ApprovalPolicy { session, .. }
        | UiEvent::PermissionPreset { session, .. }
        | UiEvent::AgentPreset { session, .. }
        | UiEvent::ReasoningEffort { session, .. }
        | UiEvent::ApprovalAsked { session, .. }
        | UiEvent::ApprovalDecided { session, .. } => Some(session),
        UiEvent::SubagentStarted { .. }
        | UiEvent::SubagentFinished { .. }
        | UiEvent::Palette { .. } => None,
    }
}

/// Register (or revive) the view for a started subagent in `views`.
pub(crate) fn upsert_subagent_view(
    views: &mut Vec<SubagentView>,
    parent: &str,
    child: &str,
    locale: Locale,
) {
    if let Some(view) = views.iter_mut().find(|view| view.id == child) {
        view.running = true;
        view.failed = false;
    } else {
        let mut transcript = Transcript::new(child.to_string());
        transcript.locale = locale;
        views.push(SubagentView {
            id: child.to_string(),
            parent: parent.to_string(),
            label: locale.trf("subagent {}", "子代理 {}", &[(views.len() + 1).to_string()]),
            running: true,
            failed: false,
            transcript,
        });
    }
}

/// Draft pieces after stripping `[image n]` chips, still in reading order.
#[derive(Clone)]
pub(crate) enum StagedBlock {
    Text(String),
    Image(crate::attachments::Attachment),
}

pub(crate) struct ClientQueuedPrompt {
    pub(crate) id: u64,
    pub(crate) blocks: Vec<StagedBlock>,
}

pub(crate) struct QueueEditState {
    pub(crate) prompt_id: u64,
    pub(crate) delete_confirm: bool,
}

pub(crate) struct QueuePreview {
    pub(crate) id: u64,
    pub(crate) ordinal: usize,
    pub(crate) summary: String,
    pub(crate) selected: bool,
    pub(crate) editing: bool,
}

pub(crate) struct PendingSteer {
    pub(crate) cells: Vec<usize>,
    pub(crate) blocks: Vec<StagedBlock>,
    /// Queue-head retries keep their original FIFO position when deferred.
    pub(crate) requeue_front: bool,
    /// Transcript generation at echo time — a `/clear` invalidates the
    /// hide handles (stale indexes must not touch the new transcript).
    pub(crate) gen: u64,
}

pub(crate) fn token_spans_in(
    buf: &str,
    attachments: &[crate::attachments::Attachment],
) -> Vec<(usize, usize, usize)> {
    let mut spans = Vec::new();
    for (idx, att) in attachments.iter().enumerate() {
        if let Some(byte) = buf.find(&att.token) {
            let start = buf[..byte].chars().count();
            spans.push((start, start + att.token.chars().count(), idx));
        }
    }
    spans.sort_unstable();
    spans
}

/// 8-char id prefix — unique enough in the picker while staying readable;
/// `/resume <prefix>` still matches against the full id.
pub(crate) fn short_id(id: &str) -> String {
    id.chars().take(8).collect()
}

/// One `/resume` row. The label is the session's human handle — the
/// harness title, else the first real prompt; the meta line carries the id
/// prefix plus age · turns (local logs) or the updated date (ACP rows with
/// no local log).
pub(crate) fn session_picker_row(
    id: &str,
    title: Option<&str>,
    local: Option<&crate::sessions::SessionSummary>,
    updated_at: Option<&str>,
) -> PickerItem {
    let short = short_id(id);
    let label = title
        .map(str::trim)
        .filter(|t| !t.is_empty())
        .map(str::to_string)
        .or_else(|| local.map(|s| s.preview.clone()))
        .filter(|s| !s.is_empty())
        .map(|s| clamp_str(&s, PICKER_LABEL_COL))
        .unwrap_or_else(|| short.clone());
    let meta = match local {
        Some(s) => format!(
            "{short:<8} · {} · {} turn{}",
            crate::sessions::age_label(s.modified),
            s.turns,
            if s.turns == 1 { "" } else { "s" },
        ),
        None => format!(
            "{short:<8} · {}",
            updated_at
                .and_then(|u| u.get(..10))
                .filter(|d| !d.is_empty())
                .unwrap_or("?"),
        ),
    };
    PickerItem {
        id: id.to_string(),
        label,
        meta,
        provider: None,
    }
}

pub(crate) fn unique_session_list_match(sessions: &[SessionListItem], prefix: &str) -> Result<String, String> {
    let matches: Vec<&SessionListItem> = sessions
        .iter()
        .filter(|s| s.id.starts_with(prefix))
        .collect();
    match matches.as_slice() {
        [one] => Ok(one.id.clone()),
        [] => Err(format!(
            "no session matches “{prefix}” — /resume lists them"
        )),
        many => match many.iter().find(|s| s.id == prefix) {
            Some(one) => Ok(one.id.clone()),
            None => Err(format!(
                "“{prefix}” is ambiguous ({} matches) — /resume lists them",
                many.len()
            )),
        },
    }
}

pub(crate) fn trim_staged_blocks(blocks: &mut Vec<StagedBlock>) {
    while matches!(blocks.first(), Some(StagedBlock::Text(t)) if t.trim().is_empty()) {
        blocks.remove(0);
    }
    while matches!(blocks.last(), Some(StagedBlock::Text(t)) if t.trim().is_empty()) {
        blocks.pop();
    }
    if let Some(StagedBlock::Text(t)) = blocks.first_mut() {
        *t = t.trim().to_string();
    }
    if let Some(StagedBlock::Text(t)) = blocks.last_mut() {
        *t = t.trim().to_string();
    }
    blocks.retain(|b| !matches!(b, StagedBlock::Text(t) if t.is_empty()));
}

/// Split a composer draft on inline image chips, preserving 图文交替.
pub(crate) fn split_draft_into_staged_blocks(
    buf: &str,
    attachments: Vec<crate::attachments::Attachment>,
) -> Vec<StagedBlock> {
    let spans = token_spans_in(buf, &attachments);
    let chars: Vec<char> = buf.chars().collect();
    let mut slots: Vec<Option<crate::attachments::Attachment>> =
        attachments.into_iter().map(Some).collect();
    let mut blocks = Vec::new();
    let mut char_i = 0usize;
    for &(start, end, idx) in &spans {
        if start > char_i {
            let text: String = chars[char_i..start.min(chars.len())].iter().collect();
            if !text.is_empty() {
                blocks.push(StagedBlock::Text(text));
            }
        }
        if let Some(att) = slots.get_mut(idx).and_then(Option::take) {
            blocks.push(StagedBlock::Image(att));
        }
        char_i = end.min(chars.len());
    }
    if char_i < chars.len() {
        let text: String = chars[char_i..].iter().collect();
        if !text.is_empty() {
            blocks.push(StagedBlock::Text(text));
        }
    }
    trim_staged_blocks(&mut blocks);
    blocks
}

pub(crate) fn image_part_from(att: &crate::attachments::Attachment) -> crate::bus::ImagePart {
    crate::bus::ImagePart {
        data: crate::pet::base64(&att.data),
        media_type: att.media_type.clone(),
        name: att.name.clone(),
        path: att.path.clone(),
    }
}

pub(crate) fn prompt_blocks_from_staged(staged: Vec<StagedBlock>) -> Vec<crate::bus::PromptBlock> {
    staged
        .into_iter()
        .map(|block| match block {
            StagedBlock::Text(text) => crate::bus::PromptBlock::Text(text),
            StagedBlock::Image(att) => crate::bus::PromptBlock::Image(image_part_from(&att)),
        })
        .collect()
}

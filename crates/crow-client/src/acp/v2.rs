//! The ACP v2 client stack.
//!
//! v2 is not v1 with the serial numbers filed off, and the difference that
//! matters most is this: **the turn does not end when `session/prompt`
//! returns.** v2's `PromptResponse` is an acknowledgement carrying nothing but
//! `_meta`; the outcome arrives later as an idle `state_update` notification.
//! Returning from the request means "accepted", not "finished".
//!
//! The rest follows from shapes: `configId` instead of `id`, a required
//! top-level permission `title` with the tool state demoted to an optional
//! `subject`, `session/resume` + `replayFrom` instead of `session/load`, and no
//! client `fs` or `terminal` capability at all — v2's `ClientCapabilities` has
//! neither field, so the v1 file and terminal handlers are not merely unused
//! here, they are unadvertiseable.
//!
//! What is shared with v1 is shared deliberately. [`super::TurnOutcome`] is the
//! protocol-neutral seam both stacks land on, so a turn ends the same way
//! whichever protocol produced it and the stop-reason vocabulary cannot drift
//! between them. The session bookkeeping — [`super::SessionHandle`], parking,
//! auth stalls, [`super::apply_prompt_finish`] — is protocol-neutral too and is
//! reused as-is. Only the wire calls are v2's own.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::{Arc, Mutex};

// v1's `SessionId` is crow's internal session-id currency: every shared
// helper (`resolve_cmd_session`, `bind_session`, `emit_session_bound`,
// `Surface`) speaks it. It is a string newtype, so the v2 wire calls convert at
// the boundary rather than the whole stack growing a second id type.
use agent_client_protocol::schema::v1::SessionId;
use agent_client_protocol::schema::v2::{
    self, ContentBlock, ImageContent, PermissionOptionKind, RequestPermissionOutcome,
    RequestPermissionResponse, ResourceLink, SelectedPermissionOutcome, TextContent,
};
use agent_client_protocol::{
    on_receive_notification, on_receive_request, Agent, Channel, Client, ConnectionTo,
    Error as AcpError, Handled, UntypedMessage,
};
use serde_json::{json, Value};
use std::sync::mpsc::{Receiver, Sender};
use tokio::sync::mpsc::UnboundedSender;

use super::control::run_version_neutral;
use super::negotiate::Negotiated;
use super::{
    abs_fs_path, acp_error_message, apply_config_response, apply_prompt_finish, apply_setup,
    auth_stalled_for, bind_session, configured_snapshot, connection_id,
    declared_auth_methods, emit_auth, emit_needs_auth_open, emit_open_auth_if_needed,
    emit_session_bound, is_auth_required_error, needs_auth_snapshot, no_session, parse_auth_methods,
    parked_prompt, process_env, prompt_image_supported, requeue_connection_prompts,
    requeue_parked_prompts, resolve_cmd_session, retarget_session, session_connection_snapshot,
    skills_from_available_commands, snapshot_from_methods, spill_image, unix_file_uri,
    AuthMethodInfo, AuthStatus, BlockTaskDeadline, ParkedPrompt, ParkedPromptKind, PromptFinish,
    SessionHandle, SteerFinish, Surface, TurnOutcome, TurnUsage,
};
use crate::bus::{
    permission_ask_empty_outcome, AppEvent, Cmd, CtlEvent, PermissionAskOption, PermissionAskReply,
    SessionListItem,
};
use crate::runtime::RuntimeConfig;

/// One slot per session with a turn in flight, fed by the idle `state_update`.
///
/// This is crow-cli's `HeadlessClient.stops` plus the arming rule it lacks.
/// agent2 re-emits `idle` every thirty seconds for the life of a parked
/// session, so an idle is only an answer when a turn is waiting for one; a
/// persistent per-session queue would let a stale heartbeat settle the next
/// prompt instantly. Arming on send and disarming on delivery is what tells a
/// turn-end from a heartbeat.
#[derive(Default)]
struct TurnBoard {
    stops: HashMap<String, UnboundedSender<TurnOutcome>>,
}

impl TurnBoard {
    /// Register the wait **before** the prompt goes out.
    ///
    /// A turn that ends fast — a slash command, an empty prompt — can reach
    /// idle before `session/prompt` returns its empty response, and arming
    /// afterwards would wait forever for a notification that already arrived.
    fn arm(&mut self, session: &str) -> tokio::sync::mpsc::UnboundedReceiver<TurnOutcome> {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        self.stops.insert(session.to_string(), tx);
        rx
    }

    fn disarm(&mut self, session: &str) {
        self.stops.remove(session);
    }

    /// Deliver an outcome to the turn waiting on this session. `false` means
    /// nobody was waiting, which is a heartbeat and not a turn-end.
    fn settle(&mut self, session: &str, outcome: TurnOutcome) -> bool {
        match self.stops.remove(session) {
            Some(tx) => tx.send(outcome).is_ok(),
            None => false,
        }
    }
}

fn board_lock(board: &Arc<Mutex<TurnBoard>>) -> std::sync::MutexGuard<'_, TurnBoard> {
    board.lock().unwrap_or_else(|error| error.into_inner())
}

fn replay_lock(window: &Arc<Mutex<ReplayWindow>>) -> std::sync::MutexGuard<'_, ReplayWindow> {
    window.lock().unwrap_or_else(|error| error.into_inner())
}

/// The sessions with a `session/resume` replay in flight.
///
/// crow echoes a prompt into the transcript the moment it sends one, and
/// v1's parser never had a `user_message` arm to echo it a second time. v2's
/// agent does send one, so forwarding it unconditionally printed every prompt
/// twice. It cannot simply be dropped, though: a `session/resume` +
/// `replayFrom` delivers the old transcript over this same `session/update`
/// stream, ahead of the resume response, and there is no local log to read it
/// back from the way v1's replay does. There the agent's copy is the only one.
///
/// Same discriminator, opposite answer — so the window between sending
/// `session/resume` and getting its response is what tells them apart.
#[derive(Default)]
struct ReplayWindow(HashSet<String>);

impl ReplayWindow {
    fn begin(&mut self, session: &str) {
        self.0.insert(session.to_string());
    }

    fn end(&mut self, session: &str) {
        self.0.remove(session);
    }

    /// Should this update reach the transcript?
    fn forwards(&self, update: &Value, session: &str) -> bool {
        !is_user_echo(update) || self.0.contains(session)
    }
}

/// Is this update the agent handing back a user prompt?
fn is_user_echo(update: &Value) -> bool {
    matches!(
        update.get("sessionUpdate").and_then(Value::as_str),
        Some("user_message" | "user_message_chunk")
    )
}

/// v2's stop reasons in the words the UI already knows. `Other` is the
/// extension arm v1's enum cannot represent, and it keeps the agent's own word
/// instead of passing for success or collapsing into "unknown".
fn stop_kind(reason: &v2::StopReason) -> Cow<'static, str> {
    match reason {
        v2::StopReason::EndTurn => Cow::Borrowed("completed"),
        v2::StopReason::MaxTokens => Cow::Borrowed("max-tokens"),
        v2::StopReason::MaxTurnRequests => Cow::Borrowed("max-turn-requests"),
        v2::StopReason::Refusal => Cow::Borrowed("blocked"),
        v2::StopReason::Cancelled => Cow::Borrowed("interrupted"),
        // agent2 sends `stopReason: "error"`; the spec's union is longer than
        // this match, and a reason that renders as "unknown" is a reason the
        // user cannot act on.
        v2::StopReason::Other(reason) => Cow::Owned(reason.clone()),
        _ => Cow::Borrowed("unknown"),
    }
}

/// v1 and v2 `Usage` are field-identical, so one shape serves both stacks.
fn turn_usage(usage: &v2::Usage) -> TurnUsage {
    TurnUsage {
        input: usage.input_tokens,
        output: usage.output_tokens,
        cached: usage.cached_read_tokens.unwrap_or(0) + usage.cached_write_tokens.unwrap_or(0),
        reasoning: usage.thought_tokens.unwrap_or(0),
    }
}

/// The connection ended with a turn still in flight. A dead child will never
/// send another notification, and the queue it would have sent it to is not
/// going to fill — waiting anyway is how a crashed agent leaves its turn
/// "running" forever.
fn closed() -> TurnOutcome {
    TurnOutcome::Failed(AcpError::new(-32000, "session closed before the turn ended"))
}

/// The state a v2 helper needs, so these take one argument instead of the
/// eleven v1's free functions carry.
#[derive(Clone)]
struct Stack {
    cx: ConnectionTo<Agent>,
    bus: Sender<AppEvent>,
    surface: Arc<Mutex<Surface>>,
    board: Arc<Mutex<TurnBoard>>,
    workspace: String,
    /// Sessions with a `session/resume` replay in flight. See [`ReplayWindow`].
    replaying: Arc<Mutex<ReplayWindow>>,
    /// Drops when the connection's main function returns, which is how a prompt
    /// task learns the child is gone. See [`closed`].
    alive: tokio::sync::watch::Receiver<bool>,
}

impl Stack {
    fn arm(&self, session: &str) -> tokio::sync::mpsc::UnboundedReceiver<TurnOutcome> {
        board_lock(&self.board).arm(session)
    }

    /// Mark a session as replaying for the window between sending
    /// `session/resume` and getting its response, which is exactly the window
    /// the agent replays the old transcript through.
    fn begin_replay(&self, session: &str) {
        replay_lock(&self.replaying).begin(session);
    }

    fn end_replay(&self, session: &str) {
        replay_lock(&self.replaying).end(session);
    }

    /// Wait for the turn's idle, racing the connection's own lifetime.
    async fn outcome(
        &self,
        session: &str,
        mut stops: tokio::sync::mpsc::UnboundedReceiver<TurnOutcome>,
    ) -> TurnOutcome {
        let mut alive = self.alive.clone();
        tokio::select! {
            outcome = stops.recv() => outcome.unwrap_or_else(closed),
            // `changed()` only ever fires here on a dropped sender: the value
            // is never updated, so this arm is exactly "the connection ended".
            ended = alive.changed() => {
                if ended.is_err() {
                    board_lock(&self.board).disarm(session);
                    closed()
                } else {
                    stops.recv().await.unwrap_or_else(closed)
                }
            }
        }
    }
}

/// Send one prompt and wait for the turn to end.
///
/// The wait is the v2 part: `session/prompt` returning is the ACK, and the
/// outcome lands on the board when the agent goes idle.
fn spawn_prompt(
    stack: &Stack,
    sid: SessionId,
    content: Vec<ContentBlock>,
    payload: ParkedPromptKind,
    gen: u64,
    done: UnboundedSender<PromptFinish>,
) -> tokio::task::JoinHandle<()> {
    // Armed here, before the send: see `TurnBoard::arm`.
    let stops = stack.arm(&sid.0);
    let stack = stack.clone();
    tokio::spawn(async move {
        let key = sid.to_string();
        let _ = stack.bus.send(AppEvent::Ui(crate::events::UiEvent::TurnStart {
            session: key.clone(),
            turn: 0,
        }));
        let _ = stack.bus.send(AppEvent::Rpc {
            method: "session.status".into(),
            params: json!({"sessionId": key, "status": "running"}),
        });
        let _ = stack.bus.send(AppEvent::Ctl(CtlEvent::PromptQueued {
            message_id: key.clone(),
            session_id: Some(key.clone()),
        }));
        let result = match stack
            .cx
            .send_request(v2::PromptRequest::new(sid.to_string(), content))
            .block_task()
            .await
        {
            // The ACK says nothing about the outcome. Wait for the idle.
            Ok(_) => stack.outcome(&key, stops).await,
            Err(err) => {
                board_lock(&stack.board).disarm(&key);
                TurnOutcome::Failed(err)
            }
        };
        let _ = done.send(PromptFinish {
            session_id: key,
            result,
            payload,
            gen,
        });
    })
}

/// A steer is another prompt sent while the active turn is in flight. It
/// belongs to that turn, so it must not open or close a second local lifecycle.
fn spawn_steer(
    stack: &Stack,
    sid: SessionId,
    content: Vec<ContentBlock>,
    message_id: u64,
    done: UnboundedSender<SteerFinish>,
) {
    let stops = stack.arm(&sid.0);
    let stack = stack.clone();
    tokio::spawn(async move {
        let key = sid.to_string();
        let result = match stack
            .cx
            .send_request(v2::PromptRequest::new(sid.to_string(), content))
            .block_task()
            .await
        {
            Ok(_) => stack.outcome(&key, stops).await,
            Err(err) => {
                board_lock(&stack.board).disarm(&key);
                TurnOutcome::Failed(err)
            }
        };
        let _ = done.send(SteerFinish { message_id, result });
    });
}

/// v2 cancellation is per-turn, so the session survives it: cancel, then prompt
/// again on the same id. agent2's own `driver.stop()` already emits the
/// cancelled idle, so the armed turn settles as `interrupted` and the existing
/// `turn_aborted` bookkeeping needs no v2 branch.
fn abort_turn(cx: &ConnectionTo<Agent>, session_id: &Option<SessionId>, bus: &Sender<AppEvent>) {
    if let Some(sid) = session_id.clone() {
        let _ = cx.send_notification(v2::CancelSessionNotification::new(sid.to_string()));
        let _ = bus.send(AppEvent::Ctl(CtlEvent::CancelRequested {
            session_id: sid.to_string(),
        }));
    }
}

/// Prompt blocks in v2's spelling. Same policy as v1: an agent that advertises
/// the `image` prompt capability gets the bytes inline; one that does not gets
/// a resource link to a file it can read itself.
fn prompt_content_blocks(
    blocks: Vec<crate::bus::PromptBlock>,
    prompt_image: bool,
    workspace: &str,
) -> Result<Vec<ContentBlock>, String> {
    let mut out = Vec::new();
    for (index, block) in blocks.into_iter().enumerate() {
        match block {
            crate::bus::PromptBlock::Text(text) => {
                if !text.is_empty() {
                    out.push(ContentBlock::Text(TextContent::new(text)));
                }
            }
            crate::bus::PromptBlock::Image(image) => {
                if prompt_image {
                    let mut content = ImageContent::new(image.data.clone(), image.media_type.clone());
                    if let Some(uri) = super::resolve_image_uri(&image.path, workspace) {
                        content = content.uri(uri);
                    }
                    out.push(ContentBlock::Image(content));
                } else {
                    let abs = match abs_fs_path(&image.path, workspace) {
                        Some(path) => path,
                        None => std::path::PathBuf::from(spill_image(&image, index)?),
                    };
                    if !abs.is_absolute() {
                        return Err(format!("cannot form file uri for {}", image.name));
                    }
                    out.push(ContentBlock::ResourceLink(
                        ResourceLink::new(image.name.clone(), unix_file_uri(&abs))
                            .mime_type(image.media_type.clone()),
                    ));
                }
            }
        }
    }
    Ok(out)
}

fn session_error(bus: &Sender<AppEvent>, sid: &SessionId, message: String) {
    let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionError {
        session_id: sid.to_string(),
        message,
    }));
}

/// Start the turn a prompt-like command asks for, or park it when there is no
/// session to start it on.
#[allow(clippy::too_many_arguments)]
fn begin_prompt(
    stack: &Stack,
    cmd: Cmd,
    session_id: &Option<SessionId>,
    parked: &mut VecDeque<ParkedPrompt>,
    methods: &[AuthMethodInfo],
    selected: Option<&AuthMethodInfo>,
    gen: u64,
    done: &UnboundedSender<PromptFinish>,
) -> Option<tokio::task::JoinHandle<()>> {
    let (payload, blocks) = match cmd {
        Cmd::Prompt { text, .. } | Cmd::Steer { text, .. } => (
            ParkedPromptKind::Text(text.clone()),
            vec![crate::bus::PromptBlock::Text(text)],
        ),
        Cmd::PromptImages { blocks, .. } | Cmd::SteerImages { blocks, .. } => {
            (ParkedPromptKind::Images(blocks.clone()), blocks)
        }
        _ => return None,
    };
    let Some(sid) = session_id.clone() else {
        parked.push_back(ParkedPrompt {
            session: None,
            kind: payload,
        });
        emit_needs_auth_open(
            &stack.bus,
            methods.to_vec(),
            selected,
            Some(no_session().to_string()),
        );
        return None;
    };
    let prompt_image = stack
        .surface
        .lock()
        .unwrap_or_else(|error| error.into_inner())
        .prompt_image_for(&sid.0);
    match prompt_content_blocks(blocks, prompt_image, &stack.workspace) {
        Ok(content) if !content.is_empty() => {
            Some(spawn_prompt(stack, sid, content, payload, gen, done.clone()))
        }
        Ok(_) => {
            session_error(&stack.bus, &sid, "empty image prompt".into());
            None
        }
        Err(err) => {
            session_error(&stack.bus, &sid, err);
            None
        }
    }
}

/// Send queued follow-ups for sessions whose turn just settled.
#[allow(clippy::too_many_arguments)]
fn drain_ready_sessions(
    stack: &Stack,
    sessions: &mut HashMap<String, SessionHandle>,
    parked: &mut VecDeque<ParkedPrompt>,
    methods: &[AuthMethodInfo],
    selected: Option<&AuthMethodInfo>,
    next_gen: &mut u64,
    done: &UnboundedSender<PromptFinish>,
) {
    let keys: Vec<String> = sessions.keys().cloned().collect();
    for key in keys {
        if auth_stalled_for(&key, parked, &stack.surface) {
            continue;
        }
        let Some(handle) = sessions.get_mut(&key) else {
            continue;
        };
        if handle.inflight.is_some() {
            continue;
        }
        let Some(next) = handle.queue.pop_front() else {
            continue;
        };
        *next_gen += 1;
        handle.inflight = begin_prompt(
            stack,
            next,
            &Some(SessionId::new(key.as_str())),
            parked,
            methods,
            selected,
            *next_gen,
            done,
        )
        .map(|task| (*next_gen, task));
    }
}

/// `session/new` with the client's tool supply attached. In ACP the client owns
/// tool supply: an agent starts with exactly the servers it is handed and
/// nothing else, so omitting them gets an agent that can only talk.
async fn new_session(
    stack: &Stack,
    cwd: &std::path::Path,
    methods: &[AuthMethodInfo],
    selected: Option<&AuthMethodInfo>,
    notice: Option<String>,
) -> Result<Option<SessionId>, AcpError> {
    let request = v2::NewSessionRequest::new(cwd.to_path_buf())
        .mcp_servers(crate::mcp_supply::wire_servers_v2());
    match stack
        .cx
        .send_request(request)
        .block_task_setup_deadline()
        .await
    {
        Ok(created) => {
            let sid = SessionId::new(created.session_id.to_string());
            apply_created(&created, &sid, stack, notice);
            if !methods.is_empty() {
                emit_auth(&stack.bus, configured_snapshot(methods.to_vec(), selected));
            }
            Ok(Some(sid))
        }
        Err(err) if is_auth_required_error(&err) => {
            emit_needs_auth_open(
                &stack.bus,
                methods.to_vec(),
                selected,
                Some(acp_error_message(&err)),
            );
            Ok(None)
        }
        Err(err) => Err(err),
    }
}

/// Re-attach to a durable session.
///
/// v2 has no `session/load`: `session/resume` with `replayFrom: start` is the
/// replaying re-attach, and the agent streams the transcript back through
/// `session/update` before it answers.
async fn resume_session(
    stack: &Stack,
    cwd: &std::path::Path,
    methods: &[AuthMethodInfo],
    selected: Option<&AuthMethodInfo>,
    id: &str,
) -> Result<Option<SessionId>, AcpError> {
    let sid = SessionId::new(id.to_string());
    let request = v2::ResumeSessionRequest::new(sid.to_string(), cwd.to_path_buf())
        .mcp_servers(crate::mcp_supply::wire_servers_v2())
        .replay_from(v2::ReplayFrom::Start(v2::ReplayFromStart::new()));
    // Every replayed update arrives before this response, so the flag is up for
    // exactly as long as the agent is replaying. See `user_echo`.
    stack.begin_replay(&sid.0);
    let resumed = stack
        .cx
        .send_request(request)
        .block_task_setup_deadline()
        .await;
    stack.end_replay(&sid.0);
    match resumed {
        Ok(setup) => {
            emit_session_bound(
                &stack.bus,
                &sid,
                Some(format!("⟲ resumed {id} — transcript from session/update")),
            );
            let value = serde_json::to_value(&setup).unwrap_or(Value::Null);
            apply_setup(&value, Some(&sid.0), &stack.surface, &stack.bus);
            if !methods.is_empty() {
                emit_auth(&stack.bus, configured_snapshot(methods.to_vec(), selected));
            }
            Ok(Some(sid))
        }
        Err(err) if is_auth_required_error(&err) => {
            emit_needs_auth_open(
                &stack.bus,
                methods.to_vec(),
                selected,
                Some(acp_error_message(&err)),
            );
            Ok(None)
        }
        Err(err) => Err(err),
    }
}

/// Bind the authoritative id before decomposing the setup snapshot into
/// session-scoped UI facts: App rejects facts belonging to a session that is
/// not current yet.
fn apply_created(
    created: &v2::NewSessionResponse,
    sid: &SessionId,
    stack: &Stack,
    notice: Option<String>,
) {
    emit_session_bound(&stack.bus, sid, notice);
    if let Ok(value) = serde_json::to_value(created) {
        apply_setup(&value, Some(&sid.0), &stack.surface, &stack.bus);
    }
}

/// A model choice rides `set_config_option` rather than the child's argv: this
/// is the one path that reaches every agent, which is why the client owns the
/// choice. The response carries the whole option array, so it is applied like
/// any other config snapshot.
async fn set_config_option(
    stack: &Stack,
    sid: &SessionId,
    config_id: &str,
    value: Value,
) -> Result<Value, AcpError> {
    let request = v2::SetSessionConfigOptionRequest::new(
        sid.to_string(),
        config_id.to_string(),
        config_value(value)?,
    );
    let response = stack
        .cx
        .send_request(request)
        .block_task_deadline()
        .await
        .map(|response| serde_json::to_value(response).unwrap_or(Value::Null))?;
    apply_config_response(&response, sid, &stack.surface, &stack.bus);
    Ok(response)
}

/// v2 config values are a tagged union and id-based options must say
/// `type: "id"`. A bare scalar is what the UI sends, so it is tagged here.
fn config_value(value: Value) -> Result<v2::SessionConfigOptionValue, AcpError> {
    let tagged = match &value {
        Value::Object(map) if map.contains_key("type") => value.clone(),
        Value::Bool(flag) => json!({ "type": "boolean", "value": flag }),
        other => json!({ "type": "id", "value": other }),
    };
    serde_json::from_value(tagged)
        .map_err(|err| AcpError::new(-32602, format!("config value: {err}")))
}

/// `session/list`, filtered the way the UI asked.
async fn list_sessions(
    stack: &Stack,
    cwd: &std::path::Path,
    requester_session_id: String,
    prefix: Option<String>,
    limit: usize,
) {
    let request = v2::ListSessionsRequest::new().cwd(cwd.to_path_buf());
    match stack
        .cx
        .send_request(request)
        .block_task_deadline()
        .await
        .map(|response| serde_json::to_value(response).unwrap_or(Value::Null))
    {
        Ok(value) => {
            let sessions = value
                .get("sessions")
                .and_then(Value::as_array)
                .map(|rows| {
                    rows.iter()
                        .filter_map(|row| {
                            Some(SessionListItem {
                                id: row.get("sessionId")?.as_str()?.to_string(),
                                title: row
                                    .get("title")
                                    .and_then(Value::as_str)
                                    .map(str::to_string),
                                updated_at: row
                                    .get("updatedAt")
                                    .and_then(Value::as_str)
                                    .map(str::to_string),
                            })
                        })
                        .filter(|item| {
                            prefix
                                .as_deref()
                                .is_none_or(|prefix| item.id.starts_with(prefix))
                        })
                        .take(limit.max(1))
                        .collect()
                })
                .unwrap_or_default();
            let _ = stack.bus.send(AppEvent::Ctl(CtlEvent::SessionList {
                requester_session_id,
                sessions,
                prefix,
                limit,
            }));
        }
        Err(err) => {
            let _ = stack
                .bus
                .send(AppEvent::Ctl(CtlEvent::SessionListUnavailable {
                    requester_session_id,
                    prefix,
                    limit,
                    error: acp_error_message(&err),
                }));
        }
    }
}

/// v2 auth is `auth/login` + `auth/logout` rather than v1's `authenticate`.
/// A non-empty `authMethods` implies both; an agent that advertises none must
/// not be asked.
async fn login(
    stack: &Stack,
    method: &AuthMethodInfo,
    values: &std::collections::BTreeMap<String, String>,
) -> Result<(), AcpError> {
    let mut request = v2::LoginAuthRequest::new(method.id.clone());
    if !values.is_empty() {
        let mut meta = serde_json::Map::new();
        for (name, value) in values {
            meta.insert(name.clone(), Value::String(value.clone()));
        }
        request = request.meta(meta);
    }
    stack
        .cx
        .send_request(request)
        .block_task_deadline()
        .await
        .map(|_| ())
}

/// Drive a v2 agent over a channel that has already negotiated.
///
/// `negotiated` is the probe's answer, adopted rather than re-asked: the peer
/// has already answered one `initialize`, and a second one is an error to a v2
/// agent that has moved on.
pub(super) async fn connect(
    channel: Channel,
    negotiated: Negotiated,
    cfg: RuntimeConfig,
    bus: Sender<AppEvent>,
    cmd_rx: Receiver<Cmd>,
) -> Result<(), AcpError> {
    let surface = Arc::new(Mutex::new(Surface::default()));
    let board = Arc::new(Mutex::new(TurnBoard::default()));

    let replaying = Arc::new(Mutex::new(ReplayWindow::default()));

    let bus_n = bus.clone();
    let surface_n = Arc::clone(&surface);
    let board_n = Arc::clone(&board);
    let replaying_n = Arc::clone(&replaying);
    let bus_u = bus.clone();
    let surface_u = Arc::clone(&surface);
    let bus_p = bus.clone();

    Client
        .v2()
        .name(env!("CARGO_PKG_NAME"))
        // One untyped handler for every notification. `session/update` is
        // forwarded as the RAW params, not a re-serialization of a typed
        // struct: schema 1.5.0's `ToolCallUpdate` has no `name` field, so a
        // typed round trip would silently drop it.
        .on_receive_notification(
            {
                async move |msg: UntypedMessage, cx| {
                    if msg.method() == "session/update" {
                        let params = msg.params().clone();
                        // The turn board first: that is what makes a prompt
                        // return at all. Rendering is the second job and must
                        // not be able to break it.
                        let session = params
                            .get("sessionId")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string();
                        if let Some(update) = params.get("update") {
                            if let Ok(parsed) =
                                serde_json::from_value::<v2::SessionUpdate>(update.clone())
                            {
                                if let v2::SessionUpdate::StateUpdate(state) = &parsed {
                                    if let v2::StateUpdate::Idle(idle) = state {
                                        let outcome = TurnOutcome::Stopped {
                                            kind: idle.stop_reason.as_ref().map_or_else(
                                                || Cow::Borrowed("completed"),
                                                stop_kind,
                                            ),
                                            usage: idle.usage.as_ref().map(turn_usage),
                                        };
                                        board_lock(&board_n).settle(&session, outcome);
                                    }
                                    // `Running` is a no-op: the send already
                                    // armed the turn. `RequiresAction` is a
                                    // no-op: the turn is still in flight.
                                }
                            }
                            if let Some(options) = update
                                .get("configOptions")
                                .or_else(|| update.get("config_options"))
                            {
                                if let Ok(mut surface) = surface_n.lock() {
                                    surface.apply_config_options(options, &bus_n, Some(&session));
                                }
                            }
                            if let Some(commands) = update
                                .get("availableCommands")
                                .or_else(|| update.get("available_commands"))
                            {
                                let skills = skills_from_available_commands(commands);
                                if let Ok(mut surface) = surface_n.lock() {
                                    surface.session_mut(Some(&session)).skills = skills.clone();
                                }
                                let _ = bus_n.send(AppEvent::Ctl(CtlEvent::Skills {
                                    session_id: Some(session.clone()),
                                    skills,
                                }));
                            }
                        }
                        // Claimed either way: an update this client drops is
                        // still an update it answered.
                        if let Some(update) = params.get("update") {
                            if !replay_lock(&replaying_n).forwards(update, &session) {
                                return Ok(Handled::Yes);
                            }
                        }
                        let _ = bus_n.send(AppEvent::Rpc {
                            method: "session/update".into(),
                            params,
                        });
                        return Ok(Handled::Yes);
                    }
                    if matches!(
                        msg.method(),
                        crate::ext::THEME_UPDATE
                            | crate::ext::THEME_REMOVE
                            | crate::ext::SLOTS_UPDATE
                            | crate::ext::COMMANDS_UPDATE
                            | crate::ext::OVERLAY_UPDATE
                            | crate::ext::APPROVALS_UPDATE
                            | crate::ext::UI_UPDATE
                    ) {
                        if let Ok(mut surface) = surface_u.lock() {
                            surface.client_compositor = true;
                        }
                        let _ = bus_u.send(AppEvent::Rpc {
                            method: msg.method().into(),
                            params: msg.params().clone(),
                        });
                        return Ok(Handled::Yes);
                    }
                    Ok(Handled::No {
                        message: (msg, cx),
                        retry: false,
                    })
                }
            },
            on_receive_notification!(),
        )
        // v2's permission request carries a REQUIRED top-level `title` and an
        // optional structured `subject`. Reading the title off the tool call,
        // as v1 does, would be reading a field that is not there.
        .on_receive_request(
            async move |req: v2::RequestPermissionRequest, responder, _cx| {
                let title = req.title.clone();
                let _ = bus_p.send(AppEvent::Rpc {
                    method: "session.event".into(),
                    params: json!({
                        "sessionId": req.session_id.to_string(),
                        "event": {
                            "type": "approval/asked",
                            "data": { "toolName": title }
                        }
                    }),
                });
                let options: Vec<PermissionAskOption> = req
                    .options
                    .iter()
                    .map(|opt| PermissionAskOption {
                        option_id: opt.option_id.to_string(),
                        kind: match opt.kind {
                            PermissionOptionKind::AllowOnce => "allow_once",
                            PermissionOptionKind::AllowAlways => "allow_always",
                            PermissionOptionKind::RejectOnce => "reject_once",
                            PermissionOptionKind::RejectAlways => "reject_always",
                            _ => "other",
                        }
                        .into(),
                        name: opt.name.clone(),
                    })
                    .collect();
                if permission_ask_empty_outcome(&options).is_some() {
                    return responder.respond(RequestPermissionResponse::new(
                        RequestPermissionOutcome::Cancelled,
                    ));
                }
                let (tx, rx) = tokio::sync::oneshot::channel();
                if bus_p
                    .send(AppEvent::PermissionAsk {
                        session_id: req.session_id.to_string(),
                        title,
                        options,
                        reply: tx,
                    })
                    .is_err()
                {
                    return responder.respond(RequestPermissionResponse::new(
                        RequestPermissionOutcome::Cancelled,
                    ));
                }
                // Wait off the dispatch loop so session/update still paints.
                tokio::spawn(async move {
                    let reply = rx.await.unwrap_or(PermissionAskReply::Cancelled);
                    let outcome = match reply {
                        PermissionAskReply::Selected(id) => {
                            RequestPermissionOutcome::Selected(SelectedPermissionOutcome::new(id))
                        }
                        PermissionAskReply::Cancelled => RequestPermissionOutcome::Cancelled,
                    };
                    let _ = responder.respond(RequestPermissionResponse::new(outcome));
                });
                Ok(())
            },
            on_receive_request!(),
        )
        .connect_with(channel, move |cx: ConnectionTo<Agent>| {
            let bus = bus;
            let surface = Arc::clone(&surface);
            let board = Arc::clone(&board);
            let replaying = Arc::clone(&replaying);
            let cfg = cfg;
            let negotiated = negotiated;
            async move {
                let _ = bus.send(AppEvent::Ctl(CtlEvent::Starting {
                    runtime: "acp2".into(),
                }));
                let init = negotiated.v2()?;
                let agent_name = negotiated.agent_name();
                let _ = bus.send(AppEvent::Ctl(CtlEvent::Initialized {
                    server: agent_name.clone(),
                    protocol: negotiated.protocol.tag(),
                }));

                let init_value = serde_json::to_value(&init).unwrap_or(Value::Null);
                // v2 capabilities are presence markers: advertising `session`
                // implies the baseline, so there is nothing left to probe for.
                let session_caps = init_value.get("capabilities").and_then(|c| c.get("session"));
                let resume = session_caps.is_some();
                if let Ok(mut surface) = surface.lock() {
                    surface.prompt_image = session_caps
                        .and_then(|c| c.get("prompt"))
                        .and_then(|p| p.get("image"))
                        .is_some()
                        || prompt_image_supported(&init_value);
                    surface.ext = crate::ext::advertised_by_agent(&init_value);
                    let mut connection = init_value.clone();
                    connection["command"] = json!(cfg.agent_argv().first());
                    connection["args"] =
                        json!(cfg.agent_argv().into_iter().skip(1).collect::<Vec<_>>());
                    connection["cwd"] = json!(cfg.workspace);
                    surface.initial_connection = Some(session_connection_snapshot(&connection));
                }
                let _ = bus.send(AppEvent::Ctl(CtlEvent::AgentCaps {
                    load_session: false,
                    list_session: session_caps
                        .is_some_and(|c| c.get("list").is_some()),
                    resume_session: resume,
                }));

                let auth_raw = init_value.get("authMethods").cloned().unwrap_or(Value::Null);
                let env = process_env();
                let methods =
                    parse_auth_methods(&auth_raw, &cfg.agent_argv(), &cfg.workspace, &env);
                let declared = declared_auth_methods(&auth_raw);
                let mut auth = snapshot_from_methods(methods.clone(), &declared, &env);
                let mut selected: Option<AuthMethodInfo> = None;
                if auth.status == AuthStatus::NeedsAuth
                    && methods.first().is_some_and(|method| method.form)
                {
                    auth = configured_snapshot(methods.clone(), None);
                    auth.status = AuthStatus::Unknown;
                }

                let (alive_tx, alive_rx) = tokio::sync::watch::channel(true);
                let stack = Stack {
                    cx: cx.clone(),
                    bus: bus.clone(),
                    surface: Arc::clone(&surface),
                    board,
                    workspace: cfg.workspace.clone(),
                    replaying,
                    alive: alive_rx,
                };

                let cwd = std::path::PathBuf::from(&cfg.workspace);
                let needs_open = auth.status == AuthStatus::NeedsAuth;
                emit_auth(&bus, auth);
                emit_open_auth_if_needed(
                    &bus,
                    if needs_open {
                        AuthStatus::NeedsAuth
                    } else {
                        AuthStatus::None
                    },
                );
                let mut session_auth_pending = false;
                let mut sessions = HashMap::<String, SessionHandle>::new();
                let mut current: Option<SessionId> = None;
                let mut pending = VecDeque::<Cmd>::new();
                let mut parked: VecDeque<ParkedPrompt> = VecDeque::new();
                let mut setup_failed = false;

                let started = match cfg.startup_session.as_deref() {
                    Some(id) => {
                        resume_session(&stack, &cwd, &methods, selected.as_ref(), id).await
                    }
                    None => new_session(&stack, &cwd, &methods, selected.as_ref(), None).await,
                };
                match started {
                    Ok(Some(sid)) => bind_session(&mut sessions, &mut current, &mut pending, sid),
                    Ok(None) => session_auth_pending = true,
                    Err(err) => {
                        setup_failed = true;
                        let _ = bus.send(AppEvent::Ctl(CtlEvent::ConnectionFailed {
                            target: agent_name.clone(),
                            error: format!("session setup: {err}"),
                        }));
                    }
                }
                if !setup_failed {
                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Ready { server: agent_name }));
                }

                let (fwd_tx, mut fwd_rx) = tokio::sync::mpsc::unbounded_channel::<Cmd>();
                std::thread::Builder::new()
                    .name("crow-acp2-cmds".into())
                    .spawn(move || {
                        while let Ok(cmd) = cmd_rx.recv() {
                            if fwd_tx.send(cmd).is_err() {
                                break;
                            }
                        }
                    })
                    .map_err(|err| AcpError::new(-32603, err.to_string()))?;

                let (prompt_done_tx, mut prompt_done_rx) =
                    tokio::sync::mpsc::unbounded_channel::<PromptFinish>();
                let (steer_done_tx, mut steer_done_rx) =
                    tokio::sync::mpsc::unbounded_channel::<SteerFinish>();
                let mut prompt_gen: u64 = 0;

                loop {
                    tokio::select! {
                        biased;
                        cmd = fwd_rx.recv() => {
                            let Some(mut cmd) = cmd else { break };
                            if current.is_none() && parked.is_empty() {
                                if let Some(kind) = parked_prompt(&cmd) {
                                    if session_auth_pending {
                                        parked.push_back(ParkedPrompt { session: None, kind });
                                        continue;
                                    }
                                    match new_session(&stack, &cwd, &methods, selected.as_ref(), None).await {
                                        Ok(Some(sid)) => {
                                            bind_session(&mut sessions, &mut current, &mut pending, sid.clone());
                                            retarget_session(&mut cmd, &sid);
                                            session_auth_pending = false;
                                        }
                                        Ok(None) => {
                                            session_auth_pending = true;
                                            parked.push_back(ParkedPrompt { session: None, kind });
                                            continue;
                                        }
                                        Err(err) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::Error(
                                                format!("session/new: {err}"))));
                                            continue;
                                        }
                                    }
                                }
                            }
                            // v2 tracks which session the chrome points at; the
                            // projection itself is the same JSON-RPC on both
                            // protocol versions, so it goes through the shared
                            // dispatcher with the queue and plugin planes.
                            if let Cmd::ActiveSession { session_id: Some(id) } = &cmd {
                                if sessions.contains_key(id) {
                                    current = Some(SessionId::new(id.clone()));
                                }
                            }
                            if !run_version_neutral(&cmd, &cx, &bus, &stack.surface).await {
                            match cmd {
                                Cmd::Prompt { session_id: cmd_session, text } => {
                                    let next = Cmd::Prompt { session_id: cmd_session.clone(), text };
                                    start_turn(&stack, next, &cmd_session, "prompt", &mut sessions,
                                        &current, &mut pending, &mut parked, &methods,
                                        selected.as_ref(), &mut prompt_gen, &prompt_done_tx);
                                }
                                Cmd::Steer { session_id: cmd_session, message_id, text } => {
                                    match resolve_cmd_session(&sessions, &current, &cmd_session, "steer") {
                                        Ok(Some(sid)) => {
                                            let prompt_image = stack.surface.lock()
                                                .unwrap_or_else(|e| e.into_inner())
                                                .prompt_image_for(&sid.0);
                                            match prompt_content_blocks(
                                                vec![crate::bus::PromptBlock::Text(text)],
                                                prompt_image, &stack.workspace) {
                                                Ok(content) => spawn_steer(&stack, sid, content,
                                                    message_id, steer_done_tx.clone()),
                                                Err(err) => {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Error(err)));
                                                }
                                            }
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionError {
                                                session_id: cmd_session, message }));
                                        }
                                    }
                                }
                                Cmd::PromptImages { session_id: cmd_session, blocks } => {
                                    let next = Cmd::PromptImages {
                                        session_id: cmd_session.clone(), blocks };
                                    start_turn(&stack, next, &cmd_session, "prompt", &mut sessions,
                                        &current, &mut pending, &mut parked, &methods,
                                        selected.as_ref(), &mut prompt_gen, &prompt_done_tx);
                                }
                                Cmd::SteerImages { session_id: cmd_session, message_id, blocks } => {
                                    match resolve_cmd_session(&sessions, &current, &cmd_session, "steer") {
                                        Ok(Some(sid)) => {
                                            let prompt_image = stack.surface.lock()
                                                .unwrap_or_else(|e| e.into_inner())
                                                .prompt_image_for(&sid.0);
                                            match prompt_content_blocks(blocks, prompt_image,
                                                &stack.workspace) {
                                                Ok(content) => spawn_steer(&stack, sid, content,
                                                    message_id, steer_done_tx.clone()),
                                                Err(err) => {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Error(err)));
                                                }
                                            }
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionError {
                                                session_id: cmd_session, message }));
                                        }
                                    }
                                }
                                Cmd::Interrupt { session_id: cmd_session } => {
                                    let sid = resolve_cmd_session(&sessions, &current, &cmd_session, "interrupt")
                                        .unwrap_or_else(|_| current.clone());
                                    abort_turn(&cx, &sid, &bus);
                                    if let Some(sid) = sid {
                                        let key = sid.to_string();
                                        if let Some(handle) = sessions.get_mut(&key) {
                                            handle.turn_aborted = true;
                                        }
                                    }
                                }
                                Cmd::NewSession { requester, .. } => {
                                    match new_session(&stack, &cwd, &methods, selected.as_ref(), None).await {
                                        Ok(Some(sid)) => {
                                            bind_session(&mut sessions, &mut current, &mut pending, sid);
                                            session_auth_pending = false;
                                            if let Some(requester) = requester {
                                                let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionBound {
                                                    session_id: requester, notice: None }));
                                            }
                                        }
                                        Ok(None) => session_auth_pending = true,
                                        Err(err) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::Error(
                                                format!("session/new: {err}"))));
                                        }
                                    }
                                }
                                Cmd::ResumeSession { session_id } => {
                                    match resume_session(&stack, &cwd, &methods, selected.as_ref(),
                                        &session_id).await {
                                        Ok(Some(sid)) => {
                                            bind_session(&mut sessions, &mut current, &mut pending, sid);
                                            session_auth_pending = false;
                                        }
                                        Ok(None) => session_auth_pending = true,
                                        Err(err) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                session_id, message: format!("session/resume: {err}") }));
                                        }
                                    }
                                }
                                Cmd::ListSessions { requester_session_id, prefix, limit } => {
                                    list_sessions(&stack, &cwd, requester_session_id, prefix, limit).await;
                                }
                                Cmd::ForgetSession { session_id } => {
                                    // v2 HAS session/close, unlike v1: the server-side
                                    // session is released, not merely unwatched.
                                    parked.retain(|p| p.session.as_deref() != Some(&session_id));
                                    if sessions.remove(&session_id).is_some() {
                                        let _ = cx.send_request(
                                            v2::CloseSessionRequest::new(session_id.clone()));
                                        if current.as_ref().is_some_and(|c| c.to_string() == session_id) {
                                            current = sessions.keys().next()
                                                .map(|id| SessionId::new(id.clone()));
                                        }
                                    }
                                }
                                Cmd::FetchCatalog { session_id } => {
                                    let surface = stack.surface.lock().unwrap_or_else(|e| e.into_inner());
                                    let scoped = surface.session(&session_id);
                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Catalog {
                                        session_id: Some(session_id),
                                        models: scoped.models.clone(),
                                        presets: scoped.presets.clone(),
                                    }));
                                }
                                Cmd::FetchSkills { session_id } => {
                                    let skills = stack.surface.lock().unwrap_or_else(|e| e.into_inner())
                                        .session(&session_id).skills.clone();
                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Skills {
                                        session_id: Some(session_id), skills }));
                                }
                                Cmd::FetchEfforts { session_id, .. } => {
                                    let surface = stack.surface.lock().unwrap_or_else(|e| e.into_inner());
                                    let scoped = surface.session(&session_id);
                                    let efforts = scoped.efforts.clone();
                                    let default = scoped.effort_current.clone()
                                        .or_else(|| efforts.first().cloned());
                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Efforts {
                                        session_id: Some(session_id),
                                        efforts: if efforts.is_empty() {
                                            vec!["off".into(), "high".into(), "max".into()]
                                        } else { efforts },
                                        default,
                                    }));
                                }
                                Cmd::SelectModel { session_id, model, effort, .. } => {
                                    match resolve_cmd_session(&sessions, &current, &session_id, "model") {
                                        Ok(Some(sid)) => {
                                            if let Some(model) = model {
                                                if let Err(err) = set_config_option(&stack, &sid,
                                                    "model", Value::String(model.clone())).await {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::ModelSwitchFailed {
                                                        session_id: sid.to_string(), model: Some(model),
                                                        effort: None, message: acp_error_message(&err) }));
                                                }
                                            }
                                            if let Some(effort) = effort {
                                                let config_id = stack.surface.lock()
                                                    .unwrap_or_else(|e| e.into_inner())
                                                    .session(&sid.0).effort_config_id.clone()
                                                    .unwrap_or_else(|| "effort".into());
                                                if let Err(err) = set_config_option(&stack, &sid,
                                                    &config_id, Value::String(effort.clone())).await {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::ModelSwitchFailed {
                                                        session_id: sid.to_string(), model: None,
                                                        effort: Some(effort),
                                                        message: acp_error_message(&err) }));
                                                }
                                            }
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                session_id, message }));
                                        }
                                    }
                                }
                                Cmd::SetConfigOption { session_id, config_id, value } => {
                                    match resolve_cmd_session(&sessions, &current, &session_id, "config") {
                                        Ok(Some(sid)) => {
                                            if let Err(err) = set_config_option(&stack, &sid,
                                                &config_id, Value::String(value)).await {
                                                let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                    session_id: sid.to_string(),
                                                    message: acp_error_message(&err) }));
                                            }
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                session_id, message }));
                                        }
                                    }
                                }
                                Cmd::Authenticate { method_id, values } => {
                                    let method = methods.iter().find(|m| m.id == method_id).cloned();
                                    match method {
                                        Some(method) => match login(&stack, &method, &values).await {
                                            Ok(()) => {
                                                selected = Some(method.clone());
                                                emit_auth(&bus, configured_snapshot(methods.clone(), Some(&method)));
                                                let retried = requeue_parked_prompts(&mut sessions, &current, &mut parked);
                                                let _ = bus.send(AppEvent::Ctl(CtlEvent::TuiOpDone(
                                                    if retried > 0 {
                                                        format!("signed in — retried {retried} parked prompt{s}",
                                                            s = if retried == 1 { "" } else { "s" })
                                                    } else { "signed in".into() })));
                                                session_auth_pending = false;
                                            }
                                            Err(err) => {
                                                selected = Some(method.clone());
                                                let mut failure = needs_auth_snapshot(methods.clone(),
                                                    Some(&method), Some(acp_error_message(&err)));
                                                failure.status = AuthStatus::Failed;
                                                emit_auth(&bus, failure);
                                                let _ = bus.send(AppEvent::Ctl(CtlEvent::TuiOpFailed(
                                                    format!("authenticate: {}", acp_error_message(&err)))));
                                            }
                                        },
                                        None => {}
                                    }
                                }
                                // v2 has no `session/set_mode`: the permission
                                // preset is a config option like any other. An
                                // agent without one says so, and the badge still
                                // moves — the preset is client-side chrome first,
                                // exactly as it is on v1's fallback path.
                                Cmd::SetPermission { session_id: cmd_session, preset } => {
                                    match resolve_cmd_session(&sessions, &current, &cmd_session, "permission") {
                                        Ok(Some(sid)) => {
                                            let done = match set_config_option(&stack, &sid,
                                                "mode", Value::String(preset.clone())).await {
                                                Ok(_) => format!("permission → {preset}"),
                                                Err(err) if is_auth_required_error(&err) => {
                                                    emit_needs_auth_open(&bus, methods.clone(),
                                                        selected.as_ref(), Some(acp_error_message(&err)));
                                                    format!("permission → {preset}")
                                                }
                                                Err(err) => format!(
                                                    "permission → {preset} ({})", acp_error_message(&err)),
                                            };
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::TuiOpDone(done)));
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                session_id: cmd_session, message }));
                                        }
                                    }
                                }
                                Cmd::SetPreset { session_id: cmd_session, preset } => {
                                    match resolve_cmd_session(&sessions, &current, &cmd_session, "preset") {
                                        Ok(Some(sid)) => {
                                            let config_id = stack.surface.lock()
                                                .unwrap_or_else(|e| e.into_inner())
                                                .session(&sid.0).composition_id.clone()
                                                .unwrap_or_else(|| "agent".into());
                                            match set_config_option(&stack, &sid, &config_id,
                                                Value::String(preset.clone())).await {
                                                Ok(_) => {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::PresetSet {
                                                        session_id: sid.to_string(), preset }));
                                                }
                                                Err(err) if is_auth_required_error(&err) => {
                                                    emit_needs_auth_open(&bus, methods.clone(),
                                                        selected.as_ref(), Some(acp_error_message(&err)));
                                                }
                                                Err(err) => {
                                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::TuiOpFailed(
                                                        format!("composition switch failed: {}",
                                                            acp_error_message(&err)))));
                                                }
                                            }
                                        }
                                        Ok(None) => {}
                                        Err(message) => {
                                            let _ = bus.send(AppEvent::Ctl(CtlEvent::SessionOpFailed {
                                                session_id: cmd_session, message }));
                                        }
                                    }
                                }
                                Cmd::Shutdown => break,
                                Cmd::SwitchHarness { .. } => super::refuse_harness_switch(&bus),
                                other => {
                                    let _ = bus.send(AppEvent::Ctl(CtlEvent::Error(format!(
                                        "acp2: {:?} is not supported on a v2 connection", other))));
                                }
                            }
                            }
                        }
                        steer = steer_done_rx.recv() => {
                            if let Some(SteerFinish { message_id, result }) = steer {
                                let deferred = !result.stopped();
                                let _ = bus.send(AppEvent::Ctl(CtlEvent::SteerSettled {
                                    message_id, deferred }));
                            }
                            drain_ready_sessions(&stack, &mut sessions, &mut parked, &methods,
                                selected.as_ref(), &mut prompt_gen, &prompt_done_tx);
                        }
                        finish = prompt_done_rx.recv() => {
                            let Some(done) = finish else { continue };
                            let key = done.session_id.clone();
                            let Some(handle) = sessions.get_mut(&key) else { continue };
                            if handle.inflight.as_ref().map(|(gen, _)| *gen) != Some(done.gen) {
                                continue;
                            }
                            handle.inflight = None;
                            let aborted = std::mem::take(&mut handle.turn_aborted);
                            let agent_cancelled = done.result.cancelled();
                            if aborted && (!done.result.stopped() || agent_cancelled) {
                                let _ = bus.send(AppEvent::Ui(crate::events::UiEvent::TurnEnd {
                                    session: key.clone(), kind: "interrupted".into() }));
                                let _ = bus.send(AppEvent::Ctl(CtlEvent::Interrupted {
                                    session_id: key.clone() }));
                            } else {
                                let ok = done.result.stopped();
                                apply_prompt_finish(done, &mut parked, &bus, &methods, selected.as_ref());
                                if ok && !parked.is_empty() {
                                    requeue_connection_prompts(&mut sessions, &current, &mut parked,
                                        &stack.surface, connection_id(&stack.surface, &key).as_deref());
                                }
                            }
                            let queued = !auth_stalled_for(&key, &parked, &stack.surface)
                                && sessions.get(&key).is_some_and(|h| !h.queue.is_empty());
                            if queued {
                                drain_ready_sessions(&stack, &mut sessions, &mut parked, &methods,
                                    selected.as_ref(), &mut prompt_gen, &prompt_done_tx);
                            } else {
                                let _ = bus.send(AppEvent::Rpc {
                                    method: "session.status".into(),
                                    params: json!({"sessionId": key, "status": "idle"}),
                                });
                            }
                        }
                    }
                    drain_ready_sessions(&stack, &mut sessions, &mut parked, &methods,
                        selected.as_ref(), &mut prompt_gen, &prompt_done_tx);
                }
                drop(alive_tx);
                Ok(())
            }
        })
        .await
        .map(|_| ())
}

/// Route a prompt-like command: start it now, queue it behind the session's
/// active turn, or hold it until a session exists.
#[allow(clippy::too_many_arguments)]
fn start_turn(
    stack: &Stack,
    cmd: Cmd,
    cmd_session: &str,
    kind: &str,
    sessions: &mut HashMap<String, SessionHandle>,
    current: &Option<SessionId>,
    pending: &mut VecDeque<Cmd>,
    parked: &mut VecDeque<ParkedPrompt>,
    methods: &[AuthMethodInfo],
    selected: Option<&AuthMethodInfo>,
    prompt_gen: &mut u64,
    done: &UnboundedSender<PromptFinish>,
) {
    match resolve_cmd_session(sessions, current, cmd_session, kind) {
        Ok(Some(sid)) => {
            let handle = sessions.entry(sid.to_string()).or_default();
            if handle.inflight.is_some() || auth_stalled_for(&sid.0, parked, &stack.surface) {
                handle.queue.push_back(cmd);
            } else {
                *prompt_gen += 1;
                handle.inflight = begin_prompt(
                    stack,
                    cmd,
                    &Some(sid),
                    parked,
                    methods,
                    selected,
                    *prompt_gen,
                    done,
                )
                .map(|task| (*prompt_gen, task));
            }
        }
        Ok(None) => pending.push_back(cmd),
        Err(message) => {
            let _ = stack.bus.send(AppEvent::Ctl(CtlEvent::SessionError {
                session_id: cmd_session.to_string(),
                message,
            }));
        }
    }
}

#[cfg(test)]
#[path = "../../tests/unit/acp__v2_tests.rs"]
mod tests;

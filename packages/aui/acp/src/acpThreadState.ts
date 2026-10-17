import type {
  CompleteAttachment,
  MessageStatus,
  ThreadAssistantMessage,
  ThreadUserMessagePart,
  ToolApprovalOption,
} from "@assistant-ui/core";
import type {
  AcpAgentCapabilities,
  AcpAvailableCommand,
  AcpConnectionState,
  AcpContentBlock,
  AcpImplementation,
  AcpPermissionRequest,
  AcpPlanEntry,
  AcpSessionConfigOption,
  AcpSessionModeState,
  AcpSessionUpdate,
  AcpToolCallStatus,
  AcpUsage,
} from "./types";
import {
  appendContentBlock,
  applySessionUpdateToContent,
  applyToolCallUpdate,
  attachToolCallApproval,
  permissionOptionToApprovalOption,
  resolveToolCallApproval,
  userPartsFromBlock,
} from "./conversions";
import {
  applyCompactionPatch,
  appendCompactionSummary,
  compactionSummaryText,
  newCompactionPart,
  settleOpenCompactions,
  type AcpCompactionPatch,
} from "./compaction";

type AssistantPart = ThreadAssistantMessage["content"][number];

export type AcpLoadState =
  | { readonly type: "idle" }
  | { readonly type: "loading" }
  | { readonly type: "ready" }
  | { readonly type: "error"; readonly error: string };

export type AcpRunState =
  | { readonly type: "idle" }
  | { readonly type: "running"; readonly assistantId: string };

/**
 * A `session/load` replay window. The agent answers `session/load` only after
 * streaming the whole transcript back as `session/update` notifications, and
 * those arrive with no run in flight — the turn they describe ended long ago.
 * Without this the reducer would drop every one of them, and opening a thread
 * would show an empty conversation the agent is perfectly able to continue.
 *
 * `seq` numbers the messages the replay mints so their ids are stable across
 * two replays of the same history: a client that loads the same thread twice
 * lands on the same ids instead of leaking duplicates.
 */
export type AcpReplayState =
  | { readonly type: "idle" }
  | { readonly type: "active"; readonly seq: number };

export type AcpUserMessage = {
  readonly role: "user";
  readonly id: string;
  readonly parentId: string | null;
  readonly createdAt: number;
  readonly content: readonly ThreadUserMessagePart[];
  readonly attachments: readonly CompleteAttachment[];
};

export type AcpAssistantMessage = {
  readonly role: "assistant";
  readonly id: string;
  readonly parentId: string | null;
  readonly createdAt: number;
  readonly status: MessageStatus;
  readonly content: readonly AssistantPart[];
};

export type AcpThreadMessage = AcpUserMessage | AcpAssistantMessage;

export type AcpPendingPermission = {
  readonly approvalId: string;
  readonly toolCallId: string;
  readonly options: readonly ToolApprovalOption[];
};

export type AcpThreadState = {
  readonly loadState: AcpLoadState;
  readonly connectionState: AcpConnectionState;
  readonly sessionId: string | undefined;
  readonly agentInfo: AcpImplementation | undefined;
  readonly agentCapabilities: AcpAgentCapabilities | undefined;
  readonly messageOrder: readonly string[];
  readonly messagesById: Readonly<Record<string, AcpThreadMessage>>;
  readonly headId: string | null;
  readonly run: AcpRunState;
  readonly replay: AcpReplayState;
  readonly permissions: Readonly<Record<string, AcpPendingPermission>>;
  readonly plan: readonly AcpPlanEntry[] | undefined;
  readonly sessionTitle: string | undefined;
  readonly currentModeId: string | undefined;
  readonly availableCommands: readonly AcpAvailableCommand[] | undefined;
  readonly configOptions: readonly AcpSessionConfigOption[] | undefined;
  readonly usage: AcpUsage | undefined;
  readonly toolCallStatuses: Readonly<Record<string, AcpToolCallStatus>>;
  /**
   * `compactionId` -> the message whose content carries its `data` part. Unlike
   * `toolCallStatuses` this survives the turn that produced it: the schema lets
   * a terminal update arrive after the chunks, and a late patch that cannot find
   * its entity leaves a card spinning on a finished turn. Cleared with the
   * transcript, which is the only thing that invalidates a message id.
   */
  readonly compactionMessages: Readonly<Record<string, string>>;
};

export type AcpThreadEvent =
  | { readonly type: "load-start" }
  | { readonly type: "load-ready" }
  | { readonly type: "load-error"; readonly error: string }
  | {
      readonly type: "connection";
      readonly connectionState: AcpConnectionState;
      readonly sessionId: string | undefined;
      readonly agentInfo?: AcpImplementation | undefined;
      readonly agentCapabilities?: AcpAgentCapabilities | undefined;
      readonly sessionModes?: AcpSessionModeState | undefined;
      readonly sessionConfigOptions?:
        | readonly AcpSessionConfigOption[]
        | undefined;
    }
  | { readonly type: "append-message"; readonly message: AcpThreadMessage }
  | {
      readonly type: "replace-messages";
      readonly messages: readonly AcpThreadMessage[];
      readonly headId: string | null;
    }
  | { readonly type: "run-start"; readonly message: AcpAssistantMessage }
  | { readonly type: "replay-start" }
  | { readonly type: "replay-end" }
  | { readonly type: "session-update"; readonly update: AcpSessionUpdate }
  | {
      readonly type: "permission-request";
      readonly approvalId: string;
      readonly request: AcpPermissionRequest;
    }
  | {
      readonly type: "permission-resolved";
      readonly approvalId: string;
      readonly approved: boolean;
      readonly optionId?: string | undefined;
      readonly cancelled: boolean;
    }
  | { readonly type: "permissions-cancelled" }
  | { readonly type: "run-end"; readonly status: MessageStatus }
  | {
      readonly type: "run-handoff";
      readonly status: MessageStatus;
      readonly message: AcpAssistantMessage;
    }
  | { readonly type: "reset-thread" };

export const EMPTY_ACP_THREAD_STATE: AcpThreadState = {
  loadState: { type: "idle" },
  connectionState: "disconnected",
  sessionId: undefined,
  agentInfo: undefined,
  agentCapabilities: undefined,
  messageOrder: [],
  messagesById: {},
  headId: null,
  run: { type: "idle" },
  replay: { type: "idle" },
  permissions: {},
  plan: undefined,
  sessionTitle: undefined,
  currentModeId: undefined,
  availableCommands: undefined,
  configOptions: undefined,
  usage: undefined,
  toolCallStatuses: {},
  compactionMessages: {},
};

export const createAcpThreadState = (): AcpThreadState =>
  EMPTY_ACP_THREAD_STATE;

export const isAcpStateRunning = (state: AcpThreadState): boolean =>
  state.run.type === "running";

const withMessage = (
  state: AcpThreadState,
  message: AcpThreadMessage,
  headId: string | null = message.id,
): AcpThreadState => ({
  ...state,
  messageOrder: state.messagesById[message.id]
    ? state.messageOrder
    : [...state.messageOrder, message.id],
  messagesById: { ...state.messagesById, [message.id]: message },
  headId,
});

const runningAssistant = (
  state: AcpThreadState,
): AcpAssistantMessage | undefined => {
  if (state.run.type !== "running") return undefined;
  const message = state.messagesById[state.run.assistantId];
  return message?.role === "assistant" ? message : undefined;
};

/** A replayed turn ended before this process saw it: complete, reason unknown. */
const REPLAY_MESSAGE_STATUS: MessageStatus = {
  type: "complete",
  reason: "unknown",
};

const replayId = (seq: number) => `acp-replay-${seq}`;

/** The message at the tip of the transcript, when it has the wanted role. */
const headMessage = <T extends AcpThreadMessage["role"]>(
  state: AcpThreadState,
  role: T,
): Extract<AcpThreadMessage, { role: T }> | undefined => {
  if (state.headId === null) return undefined;
  const head = state.messagesById[state.headId];
  return head?.role === role
    ? (head as Extract<AcpThreadMessage, { role: T }>)
    : undefined;
};

const appendUserParts = (
  content: readonly ThreadUserMessagePart[],
  parts: readonly ThreadUserMessagePart[],
): readonly ThreadUserMessagePart[] => {
  const last = content[content.length - 1];
  const first = parts[0];
  if (parts.length === 1 && last?.type === "text" && first?.type === "text") {
    return [...content.slice(0, -1), { ...last, text: last.text + first.text }];
  }
  return [...content, ...parts];
};

/**
 * The message an incoming `session/update` belongs to: the run's assistant
 * while a turn is live, the transcript tip during a replay. Outside both there
 * is nothing to write into and the update is dropped — a chunk that arrives
 * after `run-end` is a late duplicate, not a reason to reopen a finished
 * message, and an agent streaming into a session nobody is running or loading
 * has no client-side target.
 */
const activeAssistant = (
  state: AcpThreadState,
): AcpAssistantMessage | undefined => {
  if (state.run.type === "running") return runningAssistant(state);
  if (state.replay.type !== "active") return undefined;
  return headMessage(state, "assistant");
};

/**
 * The assistant message a replayed update lands in, minting one when the
 * transcript tip is a user turn (or empty). History alternates, so a role
 * change at the tip is the boundary between two replayed messages — the same
 * rule the agent's own emitter follows when it starts a new message.
 */
const ensureReplayAssistant = (state: AcpThreadState): AcpThreadState => {
  if (state.replay.type !== "active") return state;
  if (headMessage(state, "assistant")) return state;
  const message: AcpAssistantMessage = {
    role: "assistant",
    id: replayId(state.replay.seq),
    parentId: state.headId,
    createdAt: Date.now(),
    status: REPLAY_MESSAGE_STATUS,
    content: [],
  };
  return {
    ...withMessage(state, message),
    replay: { type: "active", seq: state.replay.seq + 1 },
  };
};

const patchAssistant = (
  state: AcpThreadState,
  patch: (message: AcpAssistantMessage) => AcpAssistantMessage | undefined,
): AcpThreadState => {
  const message = activeAssistant(state);
  if (!message) return state;
  const next = patch(message);
  if (!next || next === message) return state;
  return {
    ...state,
    messagesById: { ...state.messagesById, [message.id]: next },
  };
};

const cancelPermissions = (state: AcpThreadState): AcpThreadState => {
  const approvalIds = Object.keys(state.permissions);
  if (approvalIds.length === 0) return state;
  let next = state;
  for (const approvalId of approvalIds) {
    next = patchAssistantAt(next, approvalId, (message) => ({
      ...message,
      content: resolveToolCallApproval(message.content, approvalId, {
        resolution: "cancelled",
      }) as AssistantPart[],
    }));
  }
  return { ...next, permissions: {} };
};

const patchAssistantAt = (
  state: AcpThreadState,
  approvalId: string,
  patch: (
    message: AcpAssistantMessage,
    approval: AcpPendingPermission,
  ) => AcpAssistantMessage | undefined,
): AcpThreadState => {
  const approval = state.permissions[approvalId];
  if (!approval) return state;
  for (const id of state.messageOrder) {
    const message = state.messagesById[id];
    if (message?.role !== "assistant") continue;
    const next = patch(message, approval);
    if (!next || next === message) continue;
    return {
      ...state,
      messagesById: { ...state.messagesById, [id]: next },
    };
  }
  return state;
};

/**
 * A whole-message assistant upsert (v2 `agent_message` / `agent_thought`).
 * Its `content` is a replacement snapshot, but for a replay — and for a live
 * agent that chose the upsert form — applying each block in order lands on the
 * same content, because the target message is empty at first sight.
 */
const applyAssistantBlocks = (
  state: AcpThreadState,
  kind: "text" | "reasoning",
  blocks: readonly AcpContentBlock[],
): AcpThreadState => {
  let next = state;
  for (const block of blocks) {
    next = patchAssistant(ensureReplayAssistant(next), (message) => {
      const content = appendContentBlock(message.content, block, kind);
      return content === undefined ? undefined : { ...message, content };
    });
  }
  return next;
};

/** A whole user-message upsert (v2 `user_message`), replay only. */
const applyUserBlocks = (
  state: AcpThreadState,
  blocks: readonly AcpContentBlock[],
): AcpThreadState => {
  let next = state;
  for (const block of blocks) {
    const parts = userPartsFromBlock(block);
    if (parts.length === 0) continue;
    const existing = headMessage(next, "user");
    if (existing) {
      next = {
        ...next,
        messagesById: {
          ...next.messagesById,
          [existing.id]: {
            ...existing,
            content: appendUserParts(existing.content, parts),
          },
        },
      };
      continue;
    }
    const seq = next.replay.type === "active" ? next.replay.seq : 0;
    const message: AcpUserMessage = {
      role: "user",
      id: replayId(seq),
      parentId: next.headId,
      createdAt: Date.now(),
      content: parts,
      attachments: [],
    };
    next = {
      ...withMessage(next, message),
      replay: { type: "active", seq: seq + 1 },
    };
  }
  return next;
};

/**
 * Patch the entity `id` names wherever its part lives, or open it in the
 * message an incoming update belongs to. The first sight of an id fixes the
 * compaction's position in the timeline — the part is appended where the update
 * arrived, between the tool calls and text around it — and every later update
 * patches that same part in place, which is what keeps a streamed summary in
 * one card instead of scattering a token per part.
 *
 * An update that arrives with no run in flight and no replay open is dropped,
 * by the same rule every other session update here follows: agent2 only ever
 * compacts inside a turn, so there is always a running assistant to write into.
 */
const upsertCompaction = (
  state: AcpThreadState,
  id: string,
  patch: AcpCompactionPatch,
): AcpThreadState => {
  const now = Date.now();
  const knownId = state.compactionMessages[id];
  const known = knownId === undefined ? undefined : state.messagesById[knownId];
  if (known?.role === "assistant") {
    const content = applyCompactionPatch(known.content, id, patch, now);
    if (content === undefined) return state;
    return {
      ...state,
      messagesById: {
        ...state.messagesById,
        [known.id]: { ...known, content },
      },
    };
  }
  const base = ensureReplayAssistant(state);
  const message = activeAssistant(base);
  if (!message) return state;
  const content =
    applyCompactionPatch(message.content, id, patch, now) ?? [
      ...message.content,
      newCompactionPart(id, patch, now),
    ];
  return {
    ...base,
    messagesById: {
      ...base.messagesById,
      [message.id]: { ...message, content },
    },
    compactionMessages: { ...base.compactionMessages, [id]: message.id },
  };
};

/**
 * One streamed summary chunk. A chunk whose id was never opened is out of spec
 * — the agent owes an `in_progress` update first — but dropping the summary on
 * the floor is worse than opening the entity late, so it upserts instead.
 */
const appendCompactionChunk = (
  state: AcpThreadState,
  id: string,
  text: string,
): AcpThreadState => {
  const knownId = state.compactionMessages[id];
  const known = knownId === undefined ? undefined : state.messagesById[knownId];
  if (known?.role === "assistant") {
    const content = appendCompactionSummary(known.content, id, text);
    if (content === undefined) return state;
    return {
      ...state,
      messagesById: {
        ...state.messagesById,
        [known.id]: { ...known, content },
      },
    };
  }
  return upsertCompaction(state, id, {
    status: "in_progress",
    summary: text,
  });
};

/**
 * Settle compactions still open when the turn ends.
 *
 * agent2 always reports its own terminal status — `cancelled` is a separate
 * branch in its `compaction.run()` precisely because `asyncio.CancelledError`
 * is a `BaseException` and `except Exception` sails past it — so this only
 * fires when the agent or the connection died mid-pass. It is not cosmetic:
 * a card left spinning is a compaction the user cannot tell from a live one.
 */
const settleCompactions = (
  state: AcpThreadState,
  status: MessageStatus,
): AcpThreadState => {
  const ids = Object.keys(state.compactionMessages);
  if (ids.length === 0) return state;
  const cancelled =
    status.type === "incomplete" && status.reason === "cancelled";
  const now = Date.now();
  let next = state;
  let settled = false;
  for (const id of ids) {
    const messageId = next.compactionMessages[id]!;
    const message = next.messagesById[messageId];
    if (message?.role !== "assistant") continue;
    const content = settleOpenCompactions(
      message.content,
      cancelled ? "cancelled" : "failed",
      cancelled ? null : "turn ended",
      now,
    );
    if (content === undefined) continue;
    next = {
      ...next,
      messagesById: {
        ...next.messagesById,
        [messageId]: { ...message, content },
      },
    };
    settled = true;
  }
  return settled ? next : state;
};

const reduceSessionUpdate = (
  state: AcpThreadState,
  update: AcpSessionUpdate,
): AcpThreadState => {
  switch (update.sessionUpdate) {
    case "plan":
      return state.plan === update.entries
        ? state
        : { ...state, plan: update.entries };
    case "session_info_update": {
      if (update.title === undefined) return state;
      const title = update.title ?? undefined;
      return state.sessionTitle === title
        ? state
        : { ...state, sessionTitle: title };
    }
    case "current_mode_update":
      return state.currentModeId === update.currentModeId
        ? state
        : { ...state, currentModeId: update.currentModeId };
    case "available_commands_update":
      return state.availableCommands === update.availableCommands
        ? state
        : { ...state, availableCommands: update.availableCommands };
    case "config_option_update":
      return state.configOptions === update.configOptions
        ? state
        : { ...state, configOptions: update.configOptions };
    case "usage_update": {
      const usage: AcpUsage = {
        used: update.used,
        size: update.size,
        cost: update.cost ?? null,
      };
      return { ...state, usage };
    }
    // Context compaction. v2 has no capability handshake for it — agent2 emits
    // these unconditionally — so these two arms are the whole of the client's
    // side. Without them the updates fall to the default arm below, which reads
    // them as tool calls, changes nothing, and leaves a compaction invisible:
    // the context meter just drops with nothing to say why.
    case "compaction_update": {
      const id = update.compactionId;
      if (typeof id !== "string" || id === "") return state;
      return upsertCompaction(state, id, {
        status: update.status,
        // Absent stays absent, which keeps what the chunks accumulated; `null`
        // and `[]` both flatten to "" and read as the explicit clear they are.
        ...(update.summary !== undefined && {
          summary: compactionSummaryText(update.summary),
        }),
        ...(update.error !== undefined && { error: update.error }),
      });
    }
    case "compaction_summary_chunk": {
      const id = update.compactionId;
      if (typeof id !== "string" || id === "" || !update.content) return state;
      const text = compactionSummaryText([update.content]);
      if (text === "") return state;
      return appendCompactionChunk(state, id, text);
    }
    case "user_message_chunk": {
      // Live, the user's turn is already on screen — the controller appended it
      // before prompting, so echoing it back would double it. In a replay it is
      // the only copy there is: the agent is handing back a turn the client
      // sent in some earlier process.
      if (state.replay.type !== "active") return state;
      const parts = userPartsFromBlock(update.content);
      if (parts.length === 0) return state;
      const existing = headMessage(state, "user");
      if (existing) {
        return {
          ...state,
          messagesById: {
            ...state.messagesById,
            [existing.id]: {
              ...existing,
              content: appendUserParts(existing.content, parts),
            },
          },
        };
      }
      const message: AcpUserMessage = {
        role: "user",
        id: replayId(state.replay.seq),
        parentId: state.headId,
        createdAt: Date.now(),
        content: parts,
        attachments: [],
      };
      return {
        ...withMessage(state, message),
        replay: { type: "active", seq: state.replay.seq + 1 },
      };
    }
    case "state_update":
      // v2's turn boundary. The client's prompt promise resolves on the idle
      // edge (and run-end is dispatched there), so the reducer has nothing to
      // move. Returning here also keeps a stray `state_update` during replay
      // from minting a spurious assistant message in the default arm.
      return state;
    case "user_message": {
      // Live echo of the accepted prompt: already on screen. In a replay the
      // whole-message upsert is the only copy there is.
      if (state.replay.type !== "active") return state;
      return applyUserBlocks(state, update.content ?? []);
    }
    case "agent_message":
      return applyAssistantBlocks(state, "text", update.content ?? []);
    case "agent_thought":
      return applyAssistantBlocks(state, "reasoning", update.content ?? []);
    case "tool_call_content_chunk": {
      // v2 streams tool output as content chunks. Fold each into its tool call
      // as a one-item content update so text keeps streaming; the default arm
      // would drop it, and an explicit arm stops it from minting during replay.
      const toolCallId = update.toolCallId;
      const knownStatus = state.toolCallStatuses[toolCallId];
      return patchAssistant(ensureReplayAssistant(state), (message) => {
        const content = applyToolCallUpdate(
          message.content,
          { toolCallId, content: [update.content] },
          knownStatus,
        );
        return content === undefined ? undefined : { ...message, content };
      });
    }
    default: {
      const toolCall = update as Parameters<
        typeof applySessionUpdateToContent
      >[1];
      const toolCallId =
        typeof toolCall.toolCallId === "string"
          ? toolCall.toolCallId
          : undefined;
      const knownStatus =
        toolCallId === undefined
          ? undefined
          : state.toolCallStatuses[toolCallId];
      // A replayed tool call or agent chunk has no run to write into, so the
      // assistant message it belongs to is minted on first contact.
      const next = patchAssistant(ensureReplayAssistant(state), (message) => {
        const content = applySessionUpdateToContent(
          message.content,
          toolCall,
          knownStatus,
        );
        return content === undefined ? undefined : { ...message, content };
      });
      const reportedStatus = toolCall.status ?? undefined;
      if (toolCallId === undefined || reportedStatus === undefined) {
        return next;
      }
      return next.toolCallStatuses[toolCallId] === reportedStatus
        ? next
        : {
            ...next,
            toolCallStatuses: {
              ...next.toolCallStatuses,
              [toolCallId]: reportedStatus,
            },
          };
    }
  }
};

export const reduceAcpThreadState = (
  state: AcpThreadState,
  event: AcpThreadEvent,
): AcpThreadState => {
  switch (event.type) {
    case "load-start":
      return state.loadState.type === "loading"
        ? state
        : { ...state, loadState: { type: "loading" } };

    case "load-ready":
      return state.loadState.type === "loading"
        ? { ...state, loadState: { type: "ready" } }
        : state;

    case "load-error":
      return { ...state, loadState: { type: "error", error: event.error } };

    case "connection":
      return {
        ...state,
        connectionState: event.connectionState,
        sessionId: event.sessionId,
        ...(event.agentInfo !== undefined && { agentInfo: event.agentInfo }),
        ...(event.agentCapabilities !== undefined && {
          agentCapabilities: event.agentCapabilities,
        }),
        ...(event.sessionModes !== undefined && {
          currentModeId: event.sessionModes.currentModeId,
        }),
        ...(event.sessionConfigOptions !== undefined && {
          configOptions: event.sessionConfigOptions,
        }),
      };

    case "append-message":
      return withMessage(state, event.message);

    case "replace-messages": {
      const messagesById: Record<string, AcpThreadMessage> = {};
      const messageOrder: string[] = [];
      for (const message of event.messages) {
        messagesById[message.id] = message;
        messageOrder.push(message.id);
      }
      return {
        ...state,
        messagesById,
        messageOrder,
        headId: event.headId,
        run: { type: "idle" },
        replay: { type: "idle" },
        permissions: {},
        toolCallStatuses: {},
        compactionMessages: {},
      };
    }

    case "run-start":
      // A live turn supersedes any replay still open: from here the run's own
      // assistant message is the only write target.
      return {
        ...withMessage(state, event.message),
        run: { type: "running", assistantId: event.message.id },
        replay: { type: "idle" },
        toolCallStatuses: {},
      };

    case "replay-start":
      return state.replay.type === "active"
        ? state
        : { ...state, replay: { type: "active", seq: 0 } };

    case "replay-end":
      return state.replay.type === "active"
        ? { ...state, replay: { type: "idle" } }
        : state;

    case "session-update":
      return reduceSessionUpdate(state, event.update);

    case "permission-request": {
      const toolCallId = event.request.toolCall.toolCallId;
      const approval = {
        id: event.approvalId,
        options: event.request.options.map(permissionOptionToApprovalOption),
      };
      const next = patchAssistant(state, (message) => ({
        ...message,
        status: { type: "requires-action", reason: "tool-calls" },
        content: attachToolCallApproval(
          message.content,
          event.request.toolCall,
          approval,
        ) as AssistantPart[],
      }));
      return {
        ...next,
        permissions: {
          ...next.permissions,
          [event.approvalId]: {
            approvalId: event.approvalId,
            toolCallId,
            options: approval.options,
          },
        },
      };
    }

    case "permission-resolved": {
      const next = patchAssistantAt(state, event.approvalId, (message) => ({
        ...message,
        status: { type: "running" },
        content: resolveToolCallApproval(message.content, event.approvalId, {
          approved: event.approved,
          ...(event.optionId !== undefined && { optionId: event.optionId }),
          ...(event.cancelled && { resolution: "cancelled" as const }),
        }) as AssistantPart[],
      }));
      const { [event.approvalId]: _removed, ...remaining } = next.permissions;
      return { ...next, permissions: remaining };
    }

    case "permissions-cancelled": {
      const next = cancelPermissions(state);
      const assistant = runningAssistant(next);
      if (!assistant || assistant.status.type !== "requires-action")
        return next;
      return patchAssistant(next, (message) => ({
        ...message,
        status: { type: "running" },
      }));
    }

    case "reset-thread":
      // A thread switch: the connection and what the agent reported about
      // itself survive, everything the previous thread said does not. Modes,
      // commands and config options are per-session too — the load that
      // follows reports the next thread's, and a fresh thread has none.
      return {
        ...state,
        messageOrder: [],
        messagesById: {},
        headId: null,
        run: { type: "idle" },
        replay: { type: "idle" },
        permissions: {},
        plan: undefined,
        sessionTitle: undefined,
        currentModeId: undefined,
        availableCommands: undefined,
        configOptions: undefined,
        usage: undefined,
        toolCallStatuses: {},
        compactionMessages: {},
      };

    case "run-end": {
      const next = cancelPermissions(state);
      const assistant = runningAssistant(next);
      const idle = !assistant
        ? { ...next, run: { type: "idle" as const } }
        : {
            ...next,
            messagesById: {
              ...next.messagesById,
              [assistant.id]: { ...assistant, status: event.status },
            },
            run: { type: "idle" as const },
          };
      return settleCompactions(idle, event.status);
    }

    case "run-handoff": {
      // A steered prompt rode behind the turn that is ending: its own turn
      // begins in the same step, so `run` never passes through idle and
      // watchers of the idle edge (a send queue draining, a scroll lock) see
      // one continuous run rather than a gap between two turns.
      const settled = cancelPermissions(state);
      const previous = runningAssistant(settled);
      const messagesById = previous
        ? {
            ...settled.messagesById,
            [previous.id]: { ...previous, status: event.status },
          }
        : settled.messagesById;
      const handedOff = {
        ...withMessage({ ...settled, messagesById }, event.message),
        run: { type: "running" as const, assistantId: event.message.id },
        replay: { type: "idle" as const },
        toolCallStatuses: {},
      };
      // The turn being handed off is over, so a compaction it left open is
      // never getting its terminal update.
      return settleCompactions(handedOff, event.status);
    }

    default:
      return state;
  }
};

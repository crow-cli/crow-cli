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
  applySessionUpdateToContent,
  attachToolCallApproval,
  permissionOptionToApprovalOption,
  resolveToolCallApproval,
  userPartsFromBlock,
} from "./conversions";

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
      };

    case "run-end": {
      const next = cancelPermissions(state);
      const assistant = runningAssistant(next);
      if (!assistant) return { ...next, run: { type: "idle" } };
      return {
        ...next,
        messagesById: {
          ...next.messagesById,
          [assistant.id]: { ...assistant, status: event.status },
        },
        run: { type: "idle" },
      };
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
      return {
        ...withMessage({ ...settled, messagesById }, event.message),
        run: { type: "running", assistantId: event.message.id },
        replay: { type: "idle" },
        toolCallStatuses: {},
      };
    }

    default:
      return state;
  }
};

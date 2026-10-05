import type { CompleteAttachment, MessageStatus, ThreadAssistantMessage, ThreadUserMessagePart, ToolApprovalOption } from "@assistant-ui/core";
import type { AcpAgentCapabilities, AcpAvailableCommand, AcpConnectionState, AcpImplementation, AcpPermissionRequest, AcpPlanEntry, AcpSessionConfigOption, AcpSessionModeState, AcpSessionUpdate, AcpToolCallStatus, AcpUsage } from "./types.js";
type AssistantPart = ThreadAssistantMessage["content"][number];
export type AcpLoadState = {
    readonly type: "idle";
} | {
    readonly type: "loading";
} | {
    readonly type: "ready";
} | {
    readonly type: "error";
    readonly error: string;
};
export type AcpRunState = {
    readonly type: "idle";
} | {
    readonly type: "running";
    readonly assistantId: string;
};
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
export type AcpReplayState = {
    readonly type: "idle";
} | {
    readonly type: "active";
    readonly seq: number;
};
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
export type AcpThreadEvent = {
    readonly type: "load-start";
} | {
    readonly type: "load-ready";
} | {
    readonly type: "load-error";
    readonly error: string;
} | {
    readonly type: "connection";
    readonly connectionState: AcpConnectionState;
    readonly sessionId: string | undefined;
    readonly agentInfo?: AcpImplementation | undefined;
    readonly agentCapabilities?: AcpAgentCapabilities | undefined;
    readonly sessionModes?: AcpSessionModeState | undefined;
    readonly sessionConfigOptions?: readonly AcpSessionConfigOption[] | undefined;
} | {
    readonly type: "append-message";
    readonly message: AcpThreadMessage;
} | {
    readonly type: "replace-messages";
    readonly messages: readonly AcpThreadMessage[];
    readonly headId: string | null;
} | {
    readonly type: "run-start";
    readonly message: AcpAssistantMessage;
} | {
    readonly type: "replay-start";
} | {
    readonly type: "replay-end";
} | {
    readonly type: "session-update";
    readonly update: AcpSessionUpdate;
} | {
    readonly type: "permission-request";
    readonly approvalId: string;
    readonly request: AcpPermissionRequest;
} | {
    readonly type: "permission-resolved";
    readonly approvalId: string;
    readonly approved: boolean;
    readonly optionId?: string | undefined;
    readonly cancelled: boolean;
} | {
    readonly type: "permissions-cancelled";
} | {
    readonly type: "run-end";
    readonly status: MessageStatus;
} | {
    readonly type: "run-handoff";
    readonly status: MessageStatus;
    readonly message: AcpAssistantMessage;
} | {
    readonly type: "reset-thread";
};
export declare const EMPTY_ACP_THREAD_STATE: AcpThreadState;
export declare const createAcpThreadState: () => AcpThreadState;
export declare const isAcpStateRunning: (state: AcpThreadState) => boolean;
export declare const reduceAcpThreadState: (state: AcpThreadState, event: AcpThreadEvent) => AcpThreadState;
export {};
import type { ThreadStep, MessageStatus, ThreadMessage, ThreadAssistantMessagePart, ThreadUserMessagePart } from "../../types/message.js";
import type { CompleteAttachment } from "../../types/attachment.js";
import type { MessageModality, MessageTiming, PartProviderMetadata, ToolCallTiming, ToolCallMessagePart, ToolCallMessagePartMcpMetadata, ToolModelContentPart, Unstable_ToolInteractionLog } from "../../types/message.js";
import type { ReadonlyJSONObject, ReadonlyJSONValue } from "assistant-stream/utils";
type DataPrefixedPart = {
    readonly type: `data-${string}`;
    readonly id?: string;
    readonly data: any;
};
type ThreadMessageLikePart = ThreadUserMessagePart | ThreadAssistantMessagePart | DataPrefixedPart | {
    readonly type: "tool-call";
    readonly toolCallId?: string;
    readonly toolName: string;
    readonly args?: ReadonlyJSONObject;
    readonly argsText?: string;
    readonly artifact?: any;
    readonly modelContent?: readonly ToolModelContentPart[] | undefined;
    readonly result?: any | undefined;
    readonly isError?: boolean | undefined;
    readonly isPreliminary?: boolean | undefined;
    readonly parentId?: string | undefined;
    readonly messages?: readonly ThreadMessage[] | undefined;
    readonly interrupt?: {
        type: "human";
        payload: unknown;
    };
    readonly timing?: ToolCallTiming;
    readonly mcp?: ToolCallMessagePartMcpMetadata;
    readonly providerMetadata?: PartProviderMetadata;
    readonly approval?: NonNullable<ToolCallMessagePart["approval"]>;
    readonly unstable_interactions?: Unstable_ToolInteractionLog;
};
export type ThreadMessageLike = {
    readonly role: "assistant" | "user" | "system";
    readonly content: string | readonly ThreadMessageLikePart[];
    readonly id?: string | undefined;
    readonly createdAt?: Date | undefined;
    readonly status?: MessageStatus | undefined;
    readonly attachments?: readonly (Omit<CompleteAttachment, "content"> & {
        readonly content: readonly (ThreadUserMessagePart | DataPrefixedPart)[];
    })[] | undefined;
    readonly metadata?: {
        readonly unstable_state?: ReadonlyJSONValue | undefined;
        readonly unstable_annotations?: readonly ReadonlyJSONValue[] | undefined;
        readonly unstable_data?: readonly ReadonlyJSONValue[] | undefined;
        readonly steps?: readonly ThreadStep[] | undefined;
        readonly timing?: MessageTiming | undefined;
        readonly submittedFeedback?: {
            readonly type: "positive" | "negative";
            readonly comment?: string;
        } | undefined;
        readonly isOptimistic?: boolean | undefined;
        readonly modality?: MessageModality | undefined;
        readonly custom?: Record<string, unknown> | undefined;
    } | undefined;
};
/**
 * @deprecated This API is experimental and may change without notice.
 */
export declare const fromThreadMessageLike: (like: ThreadMessageLike, fallbackId: string, fallbackStatus: MessageStatus) => ThreadMessage;
export {};
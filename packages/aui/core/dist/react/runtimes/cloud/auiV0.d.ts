import type { MessageStatus, PartProviderMetadata, SourceProviderMetadata, ThreadMessage, ToolCallMessagePartMcpMetadata, ToolCallTiming, ToolApprovalDisplay, ToolApprovalOption, ReasoningMessagePart, TextMessagePart, ImageMessagePart, FileMessagePart, Unstable_ToolInteractionLog } from "../../../types/message.js";
import type { CompleteAttachment } from "../../../types/attachment.js";
import type { CloudMessage } from "assistant-cloud";
import type { ReadonlyJSONObject, ReadonlyJSONValue } from "assistant-stream/utils";
import type { ToolModelContentPart } from "assistant-stream";
import type { ExportedMessageRepositoryItem } from "../../../runtime/utils/message-repository.js";
type AuiV0ToolApproval = {
    readonly id: string;
    readonly prompt?: string;
    readonly display?: ToolApprovalDisplay;
    readonly allowFreeform?: boolean;
    readonly dismissible?: boolean;
    readonly approved?: boolean;
    readonly reason?: string;
    readonly isAutomatic?: boolean;
    readonly options?: readonly ToolApprovalOption[];
    readonly optionId?: string;
    readonly text?: string;
    readonly resolution?: "cancelled" | "expired";
};
type AuiV0MessagePart = {
    readonly type: "text";
    readonly id?: string;
    readonly text: string;
    readonly providerMetadata?: NonNullable<TextMessagePart["providerMetadata"]>;
    readonly parentId?: string;
} | {
    readonly type: "reasoning";
    readonly id?: string;
    readonly text: string;
    readonly unstable_summary?: string;
    readonly providerMetadata?: NonNullable<ReasoningMessagePart["providerMetadata"]>;
    readonly parentId?: string;
} | {
    readonly type: "source";
    readonly sourceType: "url";
    readonly id: string;
    readonly url: string;
    readonly title?: string;
    readonly providerMetadata?: SourceProviderMetadata;
    readonly parentId?: string;
} | {
    readonly type: "source";
    readonly sourceType: "document";
    readonly id: string;
    readonly title: string;
    readonly mediaType: string;
    readonly filename?: string;
    readonly providerMetadata?: SourceProviderMetadata;
    readonly parentId?: string;
} | (AuiV0ToolCallPart & ({
    readonly args: ReadonlyJSONObject;
} | {
    readonly argsText: string;
})) | {
    readonly type: "image";
    readonly id?: string;
    readonly image: string;
    readonly filename?: string;
    readonly providerMetadata?: NonNullable<ImageMessagePart["providerMetadata"]>;
} | {
    readonly type: "file";
    readonly id?: string;
    readonly data: string;
    readonly mimeType: string;
    readonly filename?: string;
    readonly sourceType?: "url" | "id";
    readonly providerMetadata?: NonNullable<FileMessagePart["providerMetadata"]>;
    readonly parentId?: string;
} | {
    readonly type: "data";
    readonly id?: string;
    readonly name: string;
    readonly data: ReadonlyJSONValue;
} | {
    readonly type: "audio";
    readonly audio: {
        readonly data: string;
        readonly format: "mp3" | "wav";
    };
} | {
    readonly type: "generative-ui";
    readonly spec: ReadonlyJSONObject;
    readonly id?: string;
    readonly parentId?: string;
};
type AuiV0ToolCallPart = {
    readonly type: "tool-call";
    readonly toolCallId: string;
    readonly toolName: string;
    readonly result?: ReadonlyJSONValue;
    readonly artifact?: ReadonlyJSONValue;
    readonly modelContent?: readonly ToolModelContentPart[];
    readonly providerMetadata?: PartProviderMetadata;
    readonly isPreliminary?: true;
    readonly isError?: true;
    readonly interrupt?: {
        readonly type: "human";
        readonly payload: ReadonlyJSONValue;
    };
    readonly timing?: ToolCallTiming;
    readonly mcp?: ToolCallMessagePartMcpMetadata;
    readonly approval?: AuiV0ToolApproval;
    readonly parentId?: string;
    readonly messages?: readonly AuiV0Message[];
    readonly unstable_interactions?: Unstable_ToolInteractionLog;
};
type AuiV0AttachmentPart = {
    readonly type: "text";
    readonly id?: string;
    readonly text: string;
    readonly providerMetadata?: NonNullable<TextMessagePart["providerMetadata"]>;
    readonly parentId?: string;
} | {
    readonly type: "image";
    readonly id?: string;
    readonly image: string;
    readonly filename?: string;
    readonly providerMetadata?: NonNullable<ImageMessagePart["providerMetadata"]>;
} | {
    readonly type: "file";
    readonly id?: string;
    readonly data: string;
    readonly mimeType: string;
    readonly filename?: string;
    readonly sourceType?: "url" | "id";
    readonly providerMetadata?: NonNullable<FileMessagePart["providerMetadata"]>;
    readonly parentId?: string;
} | {
    readonly type: "audio";
    readonly audio: {
        readonly data: string;
        readonly format: "mp3" | "wav";
    };
} | {
    readonly type: "data";
    readonly id?: string;
    readonly name: string;
    readonly data: ReadonlyJSONValue;
};
type AuiV0Attachment = {
    readonly id: string;
    readonly type: CompleteAttachment["type"];
    readonly name: string;
    readonly contentType?: string;
    readonly status: CompleteAttachment["status"];
    readonly content: readonly AuiV0AttachmentPart[];
};
type AuiV0Message = {
    readonly id?: string;
    readonly createdAt?: string;
    readonly role: "assistant" | "user" | "system";
    readonly status?: MessageStatus;
    readonly content: readonly AuiV0MessagePart[];
    readonly attachments?: readonly AuiV0Attachment[];
    readonly metadata: {
        readonly unstable_state?: ReadonlyJSONValue;
        readonly unstable_annotations: readonly ReadonlyJSONValue[];
        readonly unstable_data: readonly ReadonlyJSONValue[];
        readonly steps: readonly {
            readonly usage?: {
                readonly inputTokens: number;
                readonly outputTokens: number;
            };
        }[];
        readonly custom: ReadonlyJSONObject;
    };
};
export declare function auiV0Encode(message: ThreadMessage): AuiV0Message;
/**
 * Decodes a stored row, dropping the parts, attachments and nested messages
 * that cannot be read back instead of rejecting the row, and returning null
 * when the row itself is unreadable. Loading a thread must not fail because a
 * single stored row is malformed.
 */
export declare function auiV0DecodeSafely(cloudMessage: CloudMessage & {
    format: "aui/v0";
}): ExportedMessageRepositoryItem | null;
export declare function auiV0Decode(cloudMessage: CloudMessage & {
    format: "aui/v0";
}): ExportedMessageRepositoryItem;
export {};
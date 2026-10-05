import type { FileMessagePart, ImageMessagePart, MessageStatus, TextMessagePart, ThreadAssistantMessage, ThreadUserMessage, ToolApprovalOption, ToolCallMessagePart } from "@assistant-ui/core";
import type { AcpContentBlock, AcpPermissionOption, AcpPermissionOptionKind, AcpPermissionOutcome, AcpPermissionRequest, AcpPromptCapabilities, AcpStopReason, AcpToolCallContent, AcpToolCallStatus, AcpToolCallUpdate } from "./types.js";
type AssistantPart = ThreadAssistantMessage["content"][number];
export declare function threadContentToAcpBlocks(content: ThreadUserMessage["content"]): AcpContentBlock[];
export type AcpPromptBlocks = {
    readonly blocks: AcpContentBlock[];
    readonly dropped: AcpContentBlock[];
};
/**
 * Text and resource links are the ACP baseline; every other block type has to
 * be opted into through `promptCapabilities`. An embedded resource the agent
 * cannot accept keeps whatever survives: its text travels as text, and a URI
 * the agent can fetch travels as a resource link. Inline bytes behind a
 * client-local URI survive neither way and are withheld like any other block
 * the agent cannot accept.
 */
export declare function filterPromptBlocks(blocks: readonly AcpContentBlock[], capabilities: AcpPromptCapabilities | undefined): AcpPromptBlocks;
export declare function toolCallContentToText(content: readonly AcpToolCallContent[] | null | undefined): string | undefined;
export declare function stopReasonToMessageStatus(stopReason: AcpStopReason): MessageStatus;
export declare function permissionOptionToApprovalOption(option: AcpPermissionOption): ToolApprovalOption;
export declare function isAllowKind(kind: AcpPermissionOptionKind): boolean;
export declare function isRejectKind(kind: AcpPermissionOptionKind): boolean;
export type AcpApprovalDecision = {
    readonly approvalId: string;
    readonly approved: boolean;
    readonly optionId?: string;
};
/**
 * An explicit `optionId` wins; otherwise the decision picks the first option
 * of the matching family. Never cross families — the agent supplies `options`,
 * so an `options[0]` fallback could turn a denial into a grant.
 */
export declare function resolvePermissionOutcome(request: AcpPermissionRequest, decision: AcpApprovalDecision): AcpPermissionOutcome;
/**
 * What a call is known by and what it produced, accumulated across updates and
 * kept on the part as `providerMetadata.acp`: a renderer shows `title`,
 * `toolName` is resolved from the most specific field the agent has sent so
 * far, and `content` keeps the structured blocks — a diff, a terminal
 * reference, an embedded resource — that the flattened `result` text loses.
 */
export type AcpToolCallMetadata = {
    readonly name?: string;
    readonly kind?: string;
    readonly title?: string;
    readonly content?: readonly AcpToolCallContent[];
};
export declare function buildToolCallPart(update: AcpToolCallUpdate, knownStatus?: AcpToolCallStatus | undefined): ToolCallMessagePart;
export declare function mergeToolCallPart(existing: ToolCallMessagePart, update: AcpToolCallUpdate, knownStatus?: AcpToolCallStatus | undefined): ToolCallMessagePart;
export declare function applyToolCallUpdate(content: readonly AssistantPart[], update: AcpToolCallUpdate, knownStatus?: AcpToolCallStatus | undefined): readonly AssistantPart[] | undefined;
export declare function attachToolCallApproval(content: readonly AssistantPart[], update: AcpToolCallUpdate, approval: NonNullable<ToolCallMessagePart["approval"]>): readonly AssistantPart[];
export declare function resolveToolCallApproval(content: readonly AssistantPart[], approvalId: string, resolution: Pick<NonNullable<ToolCallMessagePart["approval"]>, "approved" | "optionId" | "resolution">): readonly AssistantPart[] | undefined;
type MediaPart = TextMessagePart | ImageMessagePart | FileMessagePart;
/**
 * A content block as user-message parts. A `session/load` replay spells the
 * user's own turns as `user_message_chunk`, and those carry the same blocks a
 * prompt does — text, image, resource — so the mapping is the media one.
 */
export declare function userPartsFromBlock(block: AcpContentBlock): readonly MediaPart[];
export declare function appendContentBlock(content: readonly AssistantPart[], block: AcpContentBlock, kind: "text" | "reasoning"): readonly AssistantPart[] | undefined;
export declare function applySessionUpdateToContent(content: readonly AssistantPart[], update: {
    readonly sessionUpdate: string;
} & Partial<AcpToolCallUpdate> & {
    readonly content?: AcpContentBlock;
}, knownStatus?: AcpToolCallStatus | undefined): readonly AssistantPart[] | undefined;
export {};
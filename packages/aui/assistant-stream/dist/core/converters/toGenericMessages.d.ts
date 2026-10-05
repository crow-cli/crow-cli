/**
 * Generic message types for framework-agnostic LLM message interchange.
 * These types represent a common format that can be converted to/from
 * various LLM provider formats (AI SDK, LangChain, etc.).
 */
export type GenericTextPart = {
    type: "text";
    text: string;
};
export type GenericFilePart = {
    type: "file";
    data: string | URL;
    mediaType: string;
    filename?: string;
};
export type GenericToolCallPart = {
    type: "tool-call";
    toolCallId: string;
    toolName: string;
    args: Record<string, unknown>;
};
export type GenericToolResultPart = {
    type: "tool-result";
    toolCallId: string;
    toolName: string;
    result: unknown;
    isError?: boolean;
};
export type GenericSystemMessage = {
    role: "system";
    content: string;
};
export type GenericUserMessage = {
    role: "user";
    content: (GenericTextPart | GenericFilePart)[];
};
export type GenericAssistantMessage = {
    role: "assistant";
    content: (GenericTextPart | GenericToolCallPart)[];
};
export type GenericToolMessage = {
    role: "tool";
    content: GenericToolResultPart[];
};
export type GenericMessage = GenericSystemMessage | GenericUserMessage | GenericAssistantMessage | GenericToolMessage;
type MessagePartLike = {
    type: string;
    text?: string;
    image?: string;
    data?: string;
    mimeType?: string;
    filename?: string;
    toolCallId?: string;
    toolName?: string;
    args?: Record<string, unknown>;
    state?: string;
    result?: unknown;
    isError?: boolean;
    isPreliminary?: boolean;
    approval?: {
        approved?: boolean;
        resolution?: string;
        [key: string]: unknown;
    };
    interrupt?: unknown;
};
type AttachmentLike = {
    content: readonly MessagePartLike[];
};
type ThreadMessageLike = {
    role: "system" | "user" | "assistant";
    content: readonly MessagePartLike[];
    attachments?: readonly AttachmentLike[];
    status?: {
        type: string;
    };
};
/**
 * Converts thread messages to generic LLM messages.
 * This format can then be easily converted to provider-specific formats.
 */
export declare function toGenericMessages(messages: readonly ThreadMessageLike[]): GenericMessage[];
export {};
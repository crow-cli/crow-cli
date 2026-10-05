import type { MessageStatus } from "../../types/message.js";
import type { ReadonlyJSONValue } from "assistant-stream/utils";
import type { ThreadMessageLike } from "./thread-message-like.js";
type ThreadMessageLikeContentItem = Exclude<ThreadMessageLike["content"], string>[number];
export declare const isPendingToolCall: (c: ThreadMessageLikeContentItem) => boolean;
/** A pending tool call whose nested conversation is still streaming; the outer message stays running until the nested run settles. */
export declare const isBackgroundToolCall: (c: ThreadMessageLikeContentItem) => boolean;
export declare const isInterruptedToolCall: (c: ThreadMessageLikeContentItem) => boolean;
export declare const isAutoStatus: (status: MessageStatus) => boolean;
export declare const getAutoStatus: (isLast: boolean, isRunning: boolean, hasInterruptedToolCalls: boolean, hasPendingToolCalls: boolean, error?: ReadonlyJSONValue, isCancelled?: boolean, hasBackgroundToolCalls?: boolean) => MessageStatus;
/** Status for a message entering the repository: the nested conversation is not being fed here, so it never keeps the message running. */
export declare const getRepositoryContentAutoStatus: (content: ThreadMessageLike["content"]) => MessageStatus;
export declare const getContentAutoStatus: (content: ThreadMessageLike["content"], isLast: boolean, isRunning: boolean) => MessageStatus;
export {};
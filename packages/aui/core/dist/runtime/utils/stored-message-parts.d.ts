import type { CompleteAttachment } from "../../types/attachment.js";
import type { MessageStatus, ThreadMessage, ThreadStep } from "../../types/message.js";
export declare const MAX_STORED_MESSAGE_DEPTH = 100;
export type StoredMessagePart = Record<string, unknown> & {
    type: string;
};
export declare const parseStoredDate: (value: unknown) => Date | null;
export declare const isStoredMessageRole: (value: unknown) => value is ThreadMessage["role"];
export declare const isStoredMessageStatus: (value: unknown) => value is MessageStatus;
export declare const parseStoredThreadSteps: (value: unknown) => ThreadStep[];
export declare const isStoredMessagePart: (value: unknown) => value is StoredMessagePart;
/**
 * `fromThreadMessageLike` converts each part through its role's branch and
 * throws on a part that branch does not carry, which would cost the whole
 * stored row. The aui/v0 boundary decodes through that converter, so it filters
 * by role as well as by shape. A part type unknown to this table is left to the
 * boundary predicate, which keeps the `data-` prefixes the converter handles.
 */
export declare const isStoredAuiV0RolePart: (role: ThreadMessage["role"], value: unknown) => value is StoredMessagePart;
export declare const parseStoredAttachment: (value: unknown, isPart: (value: unknown) => value is StoredMessagePart) => CompleteAttachment | null;
export type ErrorSeverity = "critical" | "warning" | "info";
export type ErrorDisplay = "inline" | "toast" | "silent" | "dev-only";
export type AssistantErrorCode = "unknown" | "network" | "provider" | (string & {});
export type AssistantError = {
    readonly code: AssistantErrorCode;
    readonly message: string;
    readonly severity?: ErrorSeverity;
    readonly display?: ErrorDisplay;
};
export declare const isAssistantError: (value: unknown) => value is AssistantError;
declare const MESSAGE_NOT_SENT: unique symbol;
/**
 * Rejection reason for a send that never reached the backend, so nothing ran
 * and nothing is recoverable from the thread. A runtime adapter throws it from
 * `onNew` to hand the message back to the thread composer, which restores the
 * draft it cleared at dispatch time when nothing has claimed the composer
 * since. An edit composer closes at dispatch, so a rejected edit is not
 * restored.
 */
export declare class MessageNotSentError extends Error {
    readonly [MESSAGE_NOT_SENT] = true;
    constructor(message?: string);
}
export declare const isMessageNotSentError: (error: unknown) => error is MessageNotSentError;
export declare const toAssistantError: (error: unknown) => AssistantError;
export {};
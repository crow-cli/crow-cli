import type { ThreadMessage } from "../../types/message.js";
export declare const symbolInnerMessage: unique symbol;
/**
 * Attach the original external store message(s) to a ThreadMessage or message part.
 * This is a no-op if the target already has a bound message.
 * Use `getExternalStoreMessages` to retrieve the bound messages later.
 *
 * @deprecated This API is experimental and may change without notice.
 */
export declare const bindExternalStoreMessage: <T>(target: object, message: T | T[]) => void;
export declare const getExternalStoreMessages: <T>(input: {
    messages: readonly ThreadMessage[];
} | ThreadMessage | ThreadMessage["content"][number]) => T[];
export declare const FALLBACK_ID_PREFIX = "__external_store_fallback_";
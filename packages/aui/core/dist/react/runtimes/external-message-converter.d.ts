import { type ExternalMessageConverterCallback, type ExternalMessageConverterMessage, type ExternalMessageConverterMetadata, type JoinStrategy } from "../../runtime/utils/external-message-conversion.js";
export type { JoinStrategy };
export type ExternalMessageConversionCache = {
    readonly __brand: unique symbol;
};
/**
 * Creates a cache for plain external message conversion. Pass the same cache on every call for one message list, and a source message that has not changed since the previous call converts to the same `ThreadMessage` object.
 *
 * Entries are keyed by source message identity and rebuilt whenever `callback` or `metadata` is a different object than on the previous call, so keep both referentially stable.
 */
export declare const createExternalMessageConversionCache: () => ExternalMessageConversionCache;
export declare namespace useExternalMessageConverter {
    type Message = ExternalMessageConverterMessage;
    type Metadata = ExternalMessageConverterMetadata;
    type Callback<T> = ExternalMessageConverterCallback<T>;
}
export declare const convertExternalMessages: <T extends WeakKey>(messages: T[], callback: useExternalMessageConverter.Callback<T>, isRunning: boolean, metadata: useExternalMessageConverter.Metadata, cache?: ExternalMessageConversionCache) => import("../../index.js").ThreadMessage[];
export declare const useExternalMessageConverter: <T extends WeakKey>({ callback, messages, isRunning, joinStrategy, metadata, }: {
    callback: useExternalMessageConverter.Callback<T>;
    messages: T[];
    isRunning: boolean;
    joinStrategy?: JoinStrategy | undefined;
    metadata?: useExternalMessageConverter.Metadata | undefined;
}) => import("../../index.js").ThreadMessage[];
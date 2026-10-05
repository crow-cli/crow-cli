import type { ReadonlyJSONValue } from "assistant-stream/utils";
import type { ToolExecutionStatus } from "../../runtimes/tool-invocations/ToolInvocationTracker.js";
import { ThreadMessageConverter } from "../../runtimes/external-store/thread-message-converter.js";
import type { ThreadMessage } from "../../types/message.js";
import type { MessageTiming } from "../../types/message.js";
import { type ThreadMessageLike } from "./thread-message-like.js";
export type JoinStrategy = "concat-content" | "none";
export type ExternalMessageConverterMessage = (ThreadMessageLike & {
    readonly convertConfig?: {
        readonly joinStrategy?: JoinStrategy;
    };
}) | {
    role: "tool";
    toolCallId: string;
    toolName?: string | undefined;
    result: any;
    artifact?: any;
    isError?: boolean;
    messages?: readonly ThreadMessage[];
};
export type ExternalMessageConverterMetadata = {
    readonly toolStatuses?: Record<string, ToolExecutionStatus>;
    readonly error?: ReadonlyJSONValue;
    readonly cancelledMessageIds?: ReadonlySet<string>;
    readonly messageTiming?: Record<string, MessageTiming>;
};
export type ExternalMessageConverterCallback<T> = (message: T, metadata: ExternalMessageConverterMetadata) => ExternalMessageConverterMessage | ExternalMessageConverterMessage[];
export type ExternalMessageConverterCallbackResult<T> = {
    input: T;
    outputs: ExternalMessageConverterMessage[];
};
export type ExternalMessageConverterChunk<T> = {
    inputs: T[];
    outputs: ExternalMessageConverterMessage[];
};
export declare const convertExternalMessageCallback: <T>(input: T, callback: ExternalMessageConverterCallback<T>, metadata: ExternalMessageConverterMetadata) => ExternalMessageConverterCallbackResult<T>;
export declare const joinExternalMessages: (messages: readonly ExternalMessageConverterMessage[]) => ThreadMessageLike;
export declare const chunkExternalMessages: <T>(callbackResults: ExternalMessageConverterCallbackResult<T>[], joinStrategy?: JoinStrategy) => ExternalMessageConverterChunk<T>[];
export declare const shallowArrayEqual: (a: readonly unknown[], b: readonly unknown[]) => boolean;
type ExternalMessageChunkConversionCache = {
    message: ThreadMessage | undefined;
    generatedFallbackMessages: WeakSet<object>;
};
type ExternalMessageConversionCallbackCacheEntry<T> = ExternalMessageConverterCallbackResult<T> & {
    metadata: ExternalMessageConverterMetadata;
    callback: ExternalMessageConverterCallback<T>;
};
export type InternalExternalMessageConversionCache<T extends WeakKey = WeakKey> = {
    callbackCache: WeakMap<T, ExternalMessageConversionCallbackCacheEntry<T>>;
    chunkCache: WeakMap<ExternalMessageConverterMessage, ExternalMessageConverterChunk<T>>;
    converterCache: ThreadMessageConverter;
    generatedFallbackMessages: WeakSet<object>;
};
export declare const createExternalMessageConversionCache: <T extends WeakKey = WeakKey>() => InternalExternalMessageConversionCache<T>;
export declare const convertExternalMessageChunk: <T>(message: ExternalMessageConverterChunk<T>, idx: number, chunkCount: number, isRunning: boolean, error: ReadonlyJSONValue | undefined, cache?: ExternalMessageChunkConversionCache, cancelledMessageIds?: ReadonlySet<string>) => ThreadMessage;
export declare const completeExternalMessageConversion: (messages: ThreadMessage[], error: ReadonlyJSONValue | undefined) => ThreadMessage[];
export declare const convertExternalMessages: <T extends WeakKey>(messages: T[], callback: ExternalMessageConverterCallback<T>, isRunning: boolean, metadata: ExternalMessageConverterMetadata, joinStrategy?: JoinStrategy, cache?: InternalExternalMessageConversionCache<T>) => ThreadMessage[];
export {};
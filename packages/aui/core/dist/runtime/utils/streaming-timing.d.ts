import type { MessageTiming } from "../../types/message.js";
/**
 * Shape-specific accessors that adapt {@link stepStreamingTiming} /
 * {@link useStreamingTiming} to a runtime's message list. Each adapter
 * provides three pure functions over its own message type; the timing state
 * machine itself lives once in core.
 */
export type StreamingTimingAccessors<TMessage> = {
    /** Resolve the id of the last assistant message, or `undefined` if none. */
    readonly getAssistantMessageId: (messages: readonly TMessage[]) => string | undefined;
    /** Total text length (incl. reasoning/thinking) of the assistant message. */
    readonly getTextLength: (messages: readonly TMessage[], messageId: string) => number;
    /** Number of tool calls recorded on the assistant message. */
    readonly getToolCallCount: (messages: readonly TMessage[], messageId: string) => number;
};
export type StreamingTimingOptions = {
    /**
     * Estimate token count from a text length. Defaults to `Math.ceil(n / 4)`.
     * Adapters with real usage data can override this.
     */
    readonly estimateTokens?: (textLength: number) => number;
};
/**
 * Mutable tracking state for a single in-flight assistant message. Kept
 * between updates by the caller (a ref in the React hook); `null` means no
 * message is being tracked.
 *
 * `totalChunks` counts content growth deltas observed while streaming. The
 * final delta that lands in the same update as the `isRunning -> false`
 * transition is reconciled at finalize, so `totalChunks` and the token
 * estimate (derived from final length) count the same content.
 */
export type StreamingTimingState = {
    readonly messageId: string;
    readonly startTime: number;
    readonly firstTokenTime?: number;
    readonly lastContentLength: number;
    readonly totalChunks: number;
};
/**
 * Advance the client-side streaming timing tracker by one update.
 *
 * Pure: given the previous state and the current `(messages, isRunning)`
 * snapshot, returns the next state plus any `MessageTiming` finalized this
 * update (empty when streaming is still in flight). The caller owns the
 * state (e.g. a ref) and merges finalized timings into its store.
 *
 * At finalize the text length is recomputed from the final messages, and any
 * final growth delta that landed in the same update as the
 * `isRunning -> false` transition is reconciled, so the token estimate and
 * `totalChunks` count the same content (the per-adapter hooks this replaces
 * reuse a stale growth delta and miss that last chunk).
 */
export declare const stepStreamingTiming: <TMessage>(state: StreamingTimingState | null, messages: readonly TMessage[], isRunning: boolean, accessors: StreamingTimingAccessors<TMessage>, options: StreamingTimingOptions | undefined, now?: () => number) => {
    readonly state: StreamingTimingState | null;
    readonly timings: Record<string, MessageTiming>;
};
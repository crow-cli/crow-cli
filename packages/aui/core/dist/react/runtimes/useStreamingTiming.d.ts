import type { MessageTiming } from "../../types/message.js";
import { type StreamingTimingAccessors, type StreamingTimingOptions, type StreamingTimingState } from "../../runtime/utils/streaming-timing.js";
export type { StreamingTimingAccessors, StreamingTimingOptions, StreamingTimingState, };
/**
 * Tracks per-message streaming timing client-side and returns finalized
 * `MessageTiming` keyed by message id.
 *
 * Observes `isRunning` transitions and content growth through the provided
 * `accessors`, which adapt the hook to a runtime's message shape. Timing is
 * finalized when streaming ends; adapters thread the result into
 * `useExternalMessageConverter` metadata as `messageTiming`.
 *
 * @example
 * ```ts
 * const messageTiming = useStreamingTiming(messages, isRunning, {
 *   getAssistantMessageId: (msgs) => msgs.findLast((m) => m.role === "assistant")?.id,
 *   getTextLength: (msgs, id) => msgs.find((m) => m.id === id)?.content?.length ?? 0,
 *   getToolCallCount: (msgs, id) => msgs.find((m) => m.id === id)?.tool_calls?.length ?? 0,
 * });
 * ```
 */
export declare const useStreamingTiming: <TMessage>(messages: readonly TMessage[], isRunning: boolean, accessors: StreamingTimingAccessors<TMessage>, options?: StreamingTimingOptions) => Record<string, MessageTiming>;
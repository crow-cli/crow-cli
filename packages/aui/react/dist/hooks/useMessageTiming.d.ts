import type { MessageTiming } from "@assistant-ui/core";
/**
 * Hook that returns timing information for the current assistant message.
 *
 * Reads from `message.metadata.timing`.
 *
 * @example
 * ```tsx
 * function MessageStats() {
 *   const timing = useMessageTiming();
 *   if (!timing) return null;
 *   return <span>{timing.tokensPerSecond?.toFixed(1)} tok/s</span>;
 * }
 * ```
 */
export declare const useMessageTiming: () => MessageTiming | undefined;
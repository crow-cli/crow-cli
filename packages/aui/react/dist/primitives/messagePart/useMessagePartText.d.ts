import type { TextMessagePart, ReasoningMessagePart, MessagePartStatus } from "@assistant-ui/core";
/**
 * @deprecated Use {@link useAuiState} to select and narrow `s.part`.
 * Return `null` for optional rendering. Do not throw inside the selector:
 * selectors run inside `useSyncExternalStore`'s `getSnapshot`, so a transient
 * part mismatch during thread switches can unmount the React root.
 *
 * @example
 * ```tsx
 * const text = useAuiState((s) => {
 *   if (s.part.type !== "text" && s.part.type !== "reasoning") return null;
 *   return s.part;
 * });
 * ```
 *
 * See the {@link https://assistant-ui.com/docs/migrations/v0-12 migration guide}.
 */
export declare const useMessagePartText: () => (TextMessagePart & {
    readonly status: MessagePartStatus | import("@assistant-ui/core").ToolCallMessagePartStatus;
}) | (ReasoningMessagePart & {
    readonly status: MessagePartStatus | import("@assistant-ui/core").ToolCallMessagePartStatus;
});
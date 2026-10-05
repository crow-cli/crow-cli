import type { DataMessagePart } from "@assistant-ui/core";
/**
 * @deprecated Use {@link useAuiState} to select and narrow `s.part`.
 * Return `null` for optional rendering. Do not throw inside the selector:
 * selectors run inside `useSyncExternalStore`'s `getSnapshot`, so a transient
 * part mismatch during thread switches can unmount the React root.
 *
 * @example
 * ```tsx
 * const part = useAuiState((s) =>
 *   s.part.type === "data" && (!name || s.part.name === name)
 *     ? s.part
 *     : null,
 * );
 * ```
 *
 * See the {@link https://assistant-ui.com/docs/migrations/v0-12 migration guide}.
 */
export declare const useMessagePartData: <T = any>(name?: string) => DataMessagePart<T> | null;
import type { MessagePartStatus } from "@assistant-ui/core";
/**
 * @deprecated Use {@link useAuiState} to select and narrow `s.part`.
 * Return `null` for optional rendering. Do not throw inside the selector:
 * selectors run inside `useSyncExternalStore`'s `getSnapshot`, so a transient
 * part mismatch during thread switches can unmount the React root.
 *
 * @example
 * ```tsx
 * const source = useAuiState((s) => {
 *   if (s.part.type !== "source") return null;
 *   return s.part;
 * });
 * ```
 *
 * See the {@link https://assistant-ui.com/docs/migrations/v0-12 migration guide}.
 */
export declare const useMessagePartSource: () => ({
    readonly type: "source";
    readonly sourceType: "url";
    readonly id: string;
    readonly url: string;
    readonly title?: string;
    readonly providerMetadata?: import("@assistant-ui/core").SourceProviderMetadata;
    readonly parentId?: string;
} & {
    readonly status: MessagePartStatus | import("@assistant-ui/core").ToolCallMessagePartStatus;
}) | ({
    readonly type: "source";
    readonly sourceType: "document";
    readonly id: string;
    readonly url?: undefined;
    readonly title: string;
    readonly mediaType: string;
    readonly filename?: string;
    readonly providerMetadata?: import("@assistant-ui/core").SourceProviderMetadata;
    readonly parentId?: string;
} & {
    readonly status: MessagePartStatus | import("@assistant-ui/core").ToolCallMessagePartStatus;
});
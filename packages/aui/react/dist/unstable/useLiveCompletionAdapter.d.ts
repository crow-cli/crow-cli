import type { Unstable_TriggerAdapter, Unstable_TriggerItem } from "@assistant-ui/core";
export type Unstable_UseLiveCompletionAdapterOptions = {
    /**
     * Fetches the items for a query from an async source. Called debounced; the
     * resolved items are cached and returned synchronously to the popover on the
     * next render.
     */
    readonly fetcher: (query: string) => Promise<readonly Unstable_TriggerItem[]>;
    /**
     * Identifies the fetcher's data source. Change this when switching accounts,
     * workspaces, or another boundary that should invalidate cached results.
     */
    readonly cacheKey?: string | number | undefined;
    /** Debounce applied before a fetch fires, in milliseconds. @default 60 */
    readonly debounceMs?: number | undefined;
    /** When `false`, no fetch is scheduled and the adapter stays empty. @default true */
    readonly enabled?: boolean | undefined;
};
/**
 * @deprecated Under active development and may change without notice.
 *
 * Bridges an async completion source (a server search, a gateway RPC) into the
 * synchronous `Unstable_TriggerAdapter` that `ComposerTriggerPopover` consumes.
 * `search(query)` returns the last fetched items synchronously and schedules a
 * debounced fetch when the query changes; when results arrive the returned
 * `adapter` identity changes, which re-runs the popover's lookup so the fresh
 * items render. This is a search-only adapter (`categories` are empty).
 *
 * `isLoading` is `true` while a fetch is in flight. Pass it to the popover's
 * `isLoading` prop to render a loading state.
 *
 * @example
 * ```tsx
 * const mentions = unstable_useLiveCompletionAdapter({
 *   fetcher: (query) => searchUsers(query),
 * });
 *
 * <ComposerTriggerPopover
 *   char="@"
 *   adapter={mentions.adapter}
 *   isLoading={mentions.isLoading}
 *   directive={{ onInserted }}
 * />
 * ```
 */
export declare function unstable_useLiveCompletionAdapter(options: Unstable_UseLiveCompletionAdapterOptions): {
    adapter: Unstable_TriggerAdapter;
    isLoading: boolean;
};
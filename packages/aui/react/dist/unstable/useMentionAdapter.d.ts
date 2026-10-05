import { type FC } from "react";
import type { Unstable_DirectiveFormatter, Unstable_TriggerAdapter, Unstable_TriggerItem } from "@assistant-ui/core";
import type { ReadonlyJSONObject } from "assistant-stream/utils";
/** Icon component shape consumed by `ComposerTriggerPopover`'s `iconMap`. */
export type Unstable_IconComponent = FC<{
    className?: string;
}>;
export type Unstable_Mention = {
    readonly id: string;
    readonly type: string;
    readonly label: string;
    readonly description?: string | undefined;
    /** Shortcut for `metadata.icon`; merged with `metadata` if both are given. */
    readonly icon?: string | undefined;
    readonly metadata?: ReadonlyJSONObject | undefined;
};
export type Unstable_MentionCategory = {
    readonly id: string;
    readonly label: string;
    readonly items: readonly Unstable_Mention[];
};
export type Unstable_ModelContextToolsOptions = {
    /**
     * Wrap tools in a dedicated category. Selects drill-down mode on its own
     * when `categories` is unset and `items` is omitted.
     */
    readonly category?: {
        readonly id: string;
        readonly label: string;
    };
    /** Format tool name for display. */
    readonly formatLabel?: (toolName: string) => string;
    /** Default icon key for each tool. */
    readonly icon?: string;
};
export type Unstable_UseMentionAdapterOptions = {
    /**
     * Flat mention list. Ignored when `categories` is set, and keeps the
     * adapter flat when a tool `category` is configured.
     */
    readonly items?: readonly Unstable_Mention[];
    /** Categorized mentions for drill-down navigation. */
    readonly categories?: readonly Unstable_MentionCategory[];
    /**
     * How tools registered in model context integrate.
     * - `false`: exclude.
     * - `true`: include (default when no `items`/`categories`; as a category
     *   if `categories` is set, flat otherwise).
     * - object: explicit config; `category` also selects drill-down mode.
     *
     * Omitted → defaults to `true` iff neither `items` nor `categories`.
     */
    readonly includeModelContextTools?: boolean | Unstable_ModelContextToolsOptions;
    /** Directive formatter. @default unstable_defaultDirectiveFormatter */
    readonly formatter?: Unstable_DirectiveFormatter;
    /** Fires after an item is inserted into the composer. */
    readonly onInserted?: (item: Unstable_TriggerItem) => void;
    /** Maps `metadata.icon` / `category.id` string keys to React components. */
    readonly iconMap?: Record<string, Unstable_IconComponent>;
    /** Fallback icon when no entry in `iconMap` matches. */
    readonly fallbackIcon?: Unstable_IconComponent;
};
export type Unstable_MentionDirective = {
    readonly formatter: Unstable_DirectiveFormatter;
    readonly onInserted?: ((item: Unstable_TriggerItem) => void) | undefined;
};
/**
 * @deprecated Under active development and might change without notice.
 *
 * Creates a spreadable `{ adapter, directive }` bundle for `@` mentions.
 * Supports tools registered in model context, explicit items, or both —
 * flat or categorized.
 *
 * @example
 * ```tsx
 * const mention = unstable_useMentionAdapter();
 * <ComposerTriggerPopover char="@" {...mention} />
 * ```
 */
export declare function unstable_useMentionAdapter(options?: Unstable_UseMentionAdapterOptions): {
    adapter: Unstable_TriggerAdapter;
    directive: Unstable_MentionDirective;
    iconMap?: Record<string, Unstable_IconComponent>;
    fallbackIcon?: Unstable_IconComponent;
};
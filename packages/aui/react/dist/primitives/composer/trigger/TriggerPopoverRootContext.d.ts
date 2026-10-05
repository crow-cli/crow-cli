import { type FC, type ReactNode } from "react";
import type { TriggerPopoverResourceOutput } from "./TriggerPopoverResource.js";
import type { TriggerBehavior } from "./triggerSelectionResource.js";
import type { TriggerMatcher } from "./detectTrigger.js";
export type RegisteredTrigger = {
    readonly char: string;
    readonly matcher?: TriggerMatcher | undefined;
    /** Behavior contributed by a child `TriggerPopover.Directive` / `.Action`. */
    readonly behavior?: TriggerBehavior;
    readonly resource: TriggerPopoverResourceOutput;
};
export type TriggerPopoverLifecycleListener = {
    added(trigger: RegisteredTrigger): void;
    removed(char: string): void;
};
/**
 * ARIA descriptor of the popover that is currently open. Consumed by the
 * focused element (typically the composer textarea) so it can advertise the
 * combobox relationship per the WAI-ARIA editable combobox pattern.
 */
export type TriggerPopoverActiveAria = {
    popoverId: string;
    highlightedItemId: string | undefined;
};
export type TriggerPopoverRootContextValue = {
    register(trigger: RegisteredTrigger): () => void;
    getTriggers(): ReadonlyMap<string, RegisteredTrigger>;
    subscribe(listener: () => void): () => void;
    /** Subscribe to per-trigger add/remove events. */
    subscribeLifecycle(listener: TriggerPopoverLifecycleListener): () => void;
    /** ARIA descriptor of the open popover, or null if none is open. */
    getActiveAria(): TriggerPopoverActiveAria | null;
    /** Subscribe to changes in the active ARIA descriptor. */
    subscribeAria(listener: () => void): () => void;
};
/**
 * Write-side of the ARIA descriptor, scoped to `TriggerPopover` children of a
 * `TriggerPopoverRoot`. Intentionally not exposed on the public root context
 * value: external consumers can read ARIA state but cannot publish or clear it.
 */
type TriggerPopoverAriaPublish = {
    setActiveAria(char: string, aria: TriggerPopoverActiveAria | null): void;
};
export declare const useTriggerPopoverRootContext: () => TriggerPopoverRootContextValue;
export declare const useTriggerPopoverRootContextOptional: () => TriggerPopoverRootContextValue | null;
/**
 * Internal hook used by `TriggerPopover` children to publish their open and
 * highlight state. Not exported from the trigger module.
 */
export declare const useTriggerPopoverAriaPublish: () => TriggerPopoverAriaPublish;
/**
 * Live map of registered triggers, re-rendering on change. Prefer
 * `subscribeLifecycle` for incremental add/remove handling.
 */
export declare const useTriggerPopoverTriggers: () => ReadonlyMap<string, RegisteredTrigger>;
/** Like `useTriggerPopoverTriggers` but returns an empty map outside a root. */
export declare const useTriggerPopoverTriggersOptional: () => ReadonlyMap<string, RegisteredTrigger>;
/**
 * Returns the ARIA descriptor of the currently open trigger popover, or
 * `null` if none is open or the consumer is rendered outside a
 * `TriggerPopoverRoot`.
 */
export declare const useTriggerPopoverActiveAriaOptional: () => TriggerPopoverActiveAria | null;
export declare namespace ComposerPrimitiveTriggerPopoverRoot {
    type Props = {
        children: ReactNode;
    };
}
/**
 * Provider that groups one or more `TriggerPopover` declarations. Each trigger
 * is identified by its `char` (unique within the root). Behavior is contributed
 * by a child `TriggerPopover.Directive` or `TriggerPopover.Action`.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Unstable_TriggerPopoverRoot>
 *   <ComposerPrimitive.Unstable_TriggerPopover char="@" adapter={mentionAdapter}>
 *     <ComposerPrimitive.Unstable_TriggerPopover.Directive formatter={formatter} />
 *     ...
 *   </ComposerPrimitive.Unstable_TriggerPopover>
 *
 *   <ComposerPrimitive.Unstable_TriggerPopover char="/" adapter={slashAdapter}>
 *     <ComposerPrimitive.Unstable_TriggerPopover.Action onExecute={handler} />
 *     ...
 *   </ComposerPrimitive.Unstable_TriggerPopover>
 *
 *   <ComposerPrimitive.Root>
 *     <ComposerPrimitive.Input />
 *   </ComposerPrimitive.Root>
 * </ComposerPrimitive.Unstable_TriggerPopoverRoot>
 * ```
 */
export declare const ComposerPrimitiveTriggerPopoverRoot: FC<ComposerPrimitiveTriggerPopoverRoot.Props>;
export {};
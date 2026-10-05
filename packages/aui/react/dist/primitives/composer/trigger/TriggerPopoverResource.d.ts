import type { Unstable_TriggerAdapter, Unstable_TriggerCategory, Unstable_TriggerItem } from "@assistant-ui/core";
import type { AssistantClient } from "@assistant-ui/store";
import { type SelectItemOverride, type TriggerBehavior } from "./triggerSelectionResource.js";
import type { TriggerMatcher } from "./detectTrigger.js";
export type { SelectItemOverride, TriggerBehavior };
export type { TriggerPopoverKeyEvent } from "./triggerKeyboardResource.js";
/** @deprecated Use `TriggerBehavior`. */
export type OnSelectBehavior = TriggerBehavior;
export type TriggerPopoverResourceOutput = {
    readonly open: boolean;
    readonly query: string;
    readonly activeCategoryId: string | null;
    readonly categories: readonly Unstable_TriggerCategory[];
    readonly items: readonly Unstable_TriggerItem[];
    readonly highlightedIndex: number;
    readonly isSearchMode: boolean;
    /** Whether the adapter is currently resolving items (async sources). */
    readonly isLoading: boolean;
    /** Stable ID prefix for generating accessible element IDs. */
    readonly popoverId: string;
    /** ID of the currently highlighted item (for aria-activedescendant). */
    readonly highlightedItemId: string | undefined;
    selectCategory(categoryId: string): void;
    goBack(): void;
    selectItem(item: Unstable_TriggerItem): void;
    close(): void;
    /** Move the highlight to an entry index (e.g. from pointer hover). Out-of-range values are ignored. */
    highlightIndex(index: number): void;
    handleKeyDown(e: {
        readonly key: string;
        readonly shiftKey: boolean;
        preventDefault(): void;
    }): boolean;
    setCursorPosition(pos: number): void;
    registerSelectItemOverride(fn: SelectItemOverride): () => void;
};
export declare const TriggerPopoverResource: import("@assistant-ui/tap").Resource<TriggerPopoverResourceOutput, [{
    adapter: Unstable_TriggerAdapter | undefined;
    text: string;
    triggerChar: string;
    matcher: TriggerMatcher | undefined;
    behavior: TriggerBehavior | undefined;
    aui: AssistantClient;
    /** Stable ID for accessible element IDs (pass React's useId() from component layer). */
    popoverId: string;
    isLoading: boolean;
}]>;
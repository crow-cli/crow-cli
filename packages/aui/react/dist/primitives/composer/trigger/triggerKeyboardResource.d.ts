import type { Unstable_TriggerCategory, Unstable_TriggerItem } from "@assistant-ui/core";
/** Key event shape accepted by the keyboard handler. */
export type TriggerPopoverKeyEvent = {
    readonly key: string;
    readonly shiftKey: boolean;
    preventDefault(): void;
};
export type TriggerKeyboardResourceOutput = {
    /** Index of the currently highlighted entry within the navigable list. */
    readonly highlightedIndex: number;
    /** ID of the currently highlighted item (for `aria-activedescendant`). */
    readonly highlightedItemId: string | undefined;
    /** Move the highlight to an entry index (e.g. from pointer hover). Out-of-range values are ignored. */
    highlightIndex(index: number): void;
    /** Handle a key event; returns `true` if it was consumed. */
    handleKeyDown(e: TriggerPopoverKeyEvent): boolean;
};
export declare const TriggerKeyboardResource: import("@assistant-ui/tap").Resource<TriggerKeyboardResourceOutput, [{
    navigableList: readonly (Unstable_TriggerCategory | Unstable_TriggerItem)[];
    isSearchMode: boolean;
    activeCategoryId: string | null;
    query: string;
    popoverId: string;
    open: boolean;
    selectItem: (item: Unstable_TriggerItem) => void;
    selectCategory: (categoryId: string) => void;
    goBack: () => void;
    close: () => void;
}]>;
import type { Unstable_TriggerAdapter, Unstable_TriggerCategory, Unstable_TriggerItem } from "@assistant-ui/core";
export type TriggerNavigationResourceOutput = {
    /** Filtered categories visible in the list (empty in search mode). */
    readonly categories: readonly Unstable_TriggerCategory[];
    /** Filtered items visible in the list. */
    readonly items: readonly Unstable_TriggerItem[];
    /** `true` when the current list is search results rather than categories. */
    readonly isSearchMode: boolean;
    /** Currently drilled-into category id (or `null` for the top level). */
    readonly activeCategoryId: string | null;
    /** Flat list used for keyboard navigation (categories or items). */
    readonly navigableList: readonly (Unstable_TriggerCategory | Unstable_TriggerItem)[];
    /** Drill into a category. */
    selectCategory(categoryId: string): void;
    /** Return to the top-level category list. */
    goBack(): void;
};
export declare const TriggerNavigationResource: import("@assistant-ui/tap").Resource<TriggerNavigationResourceOutput, [{
    adapter: Unstable_TriggerAdapter | undefined;
    query: string;
    open: boolean;
}]>;
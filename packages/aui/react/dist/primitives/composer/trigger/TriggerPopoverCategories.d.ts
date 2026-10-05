import { Primitive } from "../../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef, type ReactNode } from "react";
import type { Unstable_TriggerCategory } from "@assistant-ui/core";
export declare namespace ComposerPrimitiveTriggerPopoverCategories {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = Omit<ComponentPropsWithoutRef<typeof Primitive.div>, "children"> & {
        children: (categories: readonly Unstable_TriggerCategory[]) => ReactNode;
    };
}
/**
 * Renders the top-level category list via a render function.
 * Only renders when no category is active and search mode is off.
 */
export declare const ComposerPrimitiveTriggerPopoverCategories: import("react").ForwardRefExoticComponent<Omit<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref">, "children"> & {
    children: (categories: readonly Unstable_TriggerCategory[]) => ReactNode;
} & import("react").RefAttributes<HTMLDivElement>>;
export declare namespace ComposerPrimitiveTriggerPopoverCategoryItem {
    type Element = ComponentRef<typeof Primitive.button>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.button> & {
        categoryId: string;
    };
}
/**
 * A button that selects a category and triggers drill-down navigation.
 * Automatically receives `data-highlighted` when keyboard-navigated.
 */
export declare const ComposerPrimitiveTriggerPopoverCategoryItem: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    categoryId: string;
} & import("react").RefAttributes<HTMLButtonElement>>;
import { Primitive } from "../../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef, type ReactNode } from "react";
import type { Unstable_TriggerItem } from "@assistant-ui/core";
export declare namespace ComposerPrimitiveTriggerPopoverItems {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = Omit<ComponentPropsWithoutRef<typeof Primitive.div>, "children"> & {
        children: (items: readonly Unstable_TriggerItem[]) => ReactNode;
    };
}
/**
 * Renders the list of items within a category or search results via a render function.
 * Only renders when a category is active or search mode is on.
 */
export declare const ComposerPrimitiveTriggerPopoverItems: import("react").ForwardRefExoticComponent<Omit<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref">, "children"> & {
    children: (items: readonly Unstable_TriggerItem[]) => ReactNode;
} & import("react").RefAttributes<HTMLDivElement>>;
export declare namespace ComposerPrimitiveTriggerPopoverItem {
    type Element = ComponentRef<typeof Primitive.button>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.button> & {
        item: Unstable_TriggerItem;
        index?: number | undefined;
    };
}
/**
 * A button that selects a trigger item.
 * Automatically receives `data-highlighted` when keyboard-navigated.
 */
export declare const ComposerPrimitiveTriggerPopoverItem: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    item: Unstable_TriggerItem;
    index?: number | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
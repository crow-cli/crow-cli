import { Primitive } from "../../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ComposerPrimitiveTriggerPopoverBack {
    type Element = ComponentRef<typeof Primitive.button>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.button>;
}
/**
 * A button that navigates back from category items to the category list.
 * Only renders when a category is active (drill-down view).
 */
export declare const ComposerPrimitiveTriggerPopoverBack: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
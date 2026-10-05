import { Primitive } from "../../utils/Primitive.js";
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
export declare namespace SelectionToolbarPrimitiveQuote {
    type Element = ComponentRef<typeof Primitive.button>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.button>;
}
/**
 * A button that quotes the currently selected text.
 *
 * Must be placed inside `SelectionToolbarPrimitive.Root`. Reads the
 * selection info from context (captured by the Root), sets it as a
 * quote in the thread composer, and clears the selection.
 *
 * @example
 * ```tsx
 * <SelectionToolbarPrimitive.Quote>
 *   <QuoteIcon /> Quote
 * </SelectionToolbarPrimitive.Quote>
 * ```
 */
export declare const SelectionToolbarPrimitiveQuote: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
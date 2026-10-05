import { Primitive } from "../../utils/Primitive.js";
import { type ElementRef, type ComponentPropsWithoutRef } from "react";
export declare namespace SuggestionPrimitiveTitle {
    type Element = ElementRef<typeof Primitive.span>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.span>;
}
/**
 * Renders the title of the suggestion.
 *
 * @example
 * ```tsx
 * <SuggestionPrimitive.Title />
 * ```
 */
export declare const SuggestionPrimitiveTitle: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref"> & import("react").RefAttributes<HTMLSpanElement>>;
import { Primitive } from "../../utils/Primitive.js";
import { type ElementRef, type ComponentPropsWithoutRef } from "react";
export declare namespace SuggestionPrimitiveDescription {
    type Element = ElementRef<typeof Primitive.span>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.span>;
}
/**
 * Renders the description/label of the suggestion.
 *
 * @example
 * ```tsx
 * <SuggestionPrimitive.Description />
 * ```
 */
export declare const SuggestionPrimitiveDescription: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref"> & import("react").RefAttributes<HTMLSpanElement>>;
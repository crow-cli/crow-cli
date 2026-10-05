import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ComposerPrimitiveQuote {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.div>;
}
/**
 * Renders a container for the quoted text preview in the composer.
 * Only renders when a quote is set.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Quote>
 *   <ComposerPrimitive.QuoteText />
 *   <ComposerPrimitive.QuoteDismiss>×</ComposerPrimitive.QuoteDismiss>
 * </ComposerPrimitive.Quote>
 * ```
 */
export declare const ComposerPrimitiveQuote: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
export declare namespace ComposerPrimitiveQuoteText {
    type Element = ComponentRef<typeof Primitive.span>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.span>;
}
/**
 * Renders the quoted text content.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.QuoteText />
 * ```
 */
export declare const ComposerPrimitiveQuoteText: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref"> & import("react").RefAttributes<HTMLSpanElement>>;
export declare namespace ComposerPrimitiveQuoteDismiss {
    type Element = ComponentRef<typeof Primitive.button>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.button>;
}
/**
 * A button that clears the current quote from the composer.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.QuoteDismiss>×</ComposerPrimitive.QuoteDismiss>
 * ```
 */
export declare const ComposerPrimitiveQuoteDismiss: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
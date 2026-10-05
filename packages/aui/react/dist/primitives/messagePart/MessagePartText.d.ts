import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef, type ElementType } from "react";
import { type SmoothOptions } from "../../utils/smooth/useSmooth.js";
export declare namespace MessagePartPrimitiveText {
    type Element = ComponentRef<typeof Primitive.span>;
    type Props = Omit<ComponentPropsWithoutRef<typeof Primitive.span>, "children" | "asChild"> & {
        /**
         * Whether to enable smooth text streaming animation.
         * When enabled, text appears with a typing effect as it streams in.
         * Pass a `SmoothOptions` object to tune the reveal rate.
         * Auto-disables under `prefers-reduced-motion: reduce`.
         * @default true
         */
        smooth?: boolean | SmoothOptions;
        /**
         * The HTML element or React component to render as.
         * Ignored when a valid `render` element is supplied.
         * @default "span"
         */
        component?: ElementType;
    };
}
/**
 * Renders the text content of a message part with optional smooth streaming.
 *
 * This component displays text content from the current message part context,
 * with support for smooth streaming animation that shows text appearing
 * character by character as it's generated.
 *
 * @example
 * ```tsx
 * <MessagePartPrimitive.Text
 *   smooth={true}
 *   component="p"
 *   className="message-text"
 * />
 * ```
 */
export declare const MessagePartPrimitiveText: import("react").ForwardRefExoticComponent<Omit<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref">, "children" | "asChild"> & {
    /**
     * Whether to enable smooth text streaming animation.
     * When enabled, text appears with a typing effect as it streams in.
     * Pass a `SmoothOptions` object to tune the reveal rate.
     * Auto-disables under `prefers-reduced-motion: reduce`.
     * @default true
     */
    smooth?: boolean | SmoothOptions;
    /**
     * The HTML element or React component to render as.
     * Ignored when a valid `render` element is supplied.
     * @default "span"
     */
    component?: ElementType;
} & import("react").RefAttributes<HTMLSpanElement>>;
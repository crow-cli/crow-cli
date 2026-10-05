import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ComposerPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.form>;
    /**
     * Props for the ComposerPrimitive.Root component.
     * Accepts all standard form element props.
     */
    type Props = ComponentPropsWithoutRef<typeof Primitive.form> & {
        /**
         * Opt the composer into compact mode. While the input holds at most a single
         * line of text and there are no attachments, quote, queued messages, or
         * active dictation, the root renders a `data-compact` attribute so styles
         * can collapse the composer into a single row. It expands automatically
         * when any of those conditions stop holding.
         * @default false
         */
        compact?: boolean | undefined;
    };
}
/**
 * The root form container for message composition.
 *
 * This component provides a form wrapper that handles message submission when the form
 * is submitted (e.g., via Enter key or submit button). It automatically prevents the
 * default form submission and triggers the composer's send functionality.
 *
 * Clicking blank form space focuses the composer input (the first textarea or
 * contenteditable inside the form). Text selection cannot start from blank
 * areas; descendants that need native mousedown defaults can call
 * `stopPropagation()` in their own `onMouseDown`.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Root>
 *   <ComposerPrimitive.Input placeholder="Type your message..." />
 *   <ComposerPrimitive.Send>Send</ComposerPrimitive.Send>
 * </ComposerPrimitive.Root>
 * ```
 */
export declare const ComposerPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLFormElement> & import("react").FormHTMLAttributes<HTMLFormElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLFormElement>, "ref"> & {
    /**
     * Opt the composer into compact mode. While the input holds at most a single
     * line of text and there are no attachments, quote, queued messages, or
     * active dictation, the root renders a `data-compact` attribute so styles
     * can collapse the composer into a single row. It expands automatically
     * when any of those conditions stop holding.
     * @default false
     */
    compact?: boolean | undefined;
} & import("react").RefAttributes<HTMLFormElement>>;
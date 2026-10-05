import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ThreadPrimitiveViewport {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.div> & {
        /**
         * Whether to automatically scroll to the bottom when new messages are added.
         * When enabled, the viewport will automatically scroll to show the latest content.
         *
         * Default false if `turnAnchor` is "top", otherwise defaults to true.
         */
        autoScroll?: boolean | undefined;
        /**
         * Controls scroll anchoring behavior for new messages.
         * - "bottom" (default): Messages anchor at the bottom, classic chat behavior.
         * - "top": New user messages anchor at the top of the viewport for a focused reading experience.
         */
        turnAnchor?: "top" | "bottom" | undefined;
        /**
         * Clamps tall user messages so the assistant response stays in view.
         *
         * @default { tallerThan: "10em", visibleHeight: "6em" }
         */
        topAnchorMessageClamp?: {
            /**
             * Clamp messages taller than this. Supports `px`, `em`, and `rem`.
             *
             * @default "10em"
             */
            tallerThan?: string;
            /**
             * Visible portion of clamped messages. Supports `px`, `em`, and `rem`.
             *
             * @default "6em"
             */
            visibleHeight?: string;
        };
        /**
         * Whether to scroll to bottom when a new run starts.
         *
         * Defaults to true.
         */
        scrollToBottomOnRunStart?: boolean | undefined;
        /**
         * Whether to scroll to bottom when thread history is first loaded.
         *
         * Defaults to true.
         */
        scrollToBottomOnInitialize?: boolean | undefined;
        /**
         * Whether to scroll to bottom when switching to a different thread.
         *
         * Defaults to true.
         */
        scrollToBottomOnThreadSwitch?: boolean | undefined;
    };
}
/**
 * A scrollable viewport container for thread messages.
 *
 * This component provides a scrollable area for displaying thread messages with
 * automatic scrolling capabilities. It manages the viewport state and provides
 * context for child components to access viewport-related functionality.
 *
 * @example
 * ```tsx
 * <ThreadPrimitive.Viewport turnAnchor="top">
 *   <ThreadPrimitive.Messages>
 *     {() => <MyMessage />}
 *   </ThreadPrimitive.Messages>
 * </ThreadPrimitive.Viewport>
 * ```
 */
export declare const ThreadPrimitiveViewport: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    /**
     * Whether to automatically scroll to the bottom when new messages are added.
     * When enabled, the viewport will automatically scroll to show the latest content.
     *
     * Default false if `turnAnchor` is "top", otherwise defaults to true.
     */
    autoScroll?: boolean | undefined;
    /**
     * Controls scroll anchoring behavior for new messages.
     * - "bottom" (default): Messages anchor at the bottom, classic chat behavior.
     * - "top": New user messages anchor at the top of the viewport for a focused reading experience.
     */
    turnAnchor?: "top" | "bottom" | undefined;
    /**
     * Clamps tall user messages so the assistant response stays in view.
     *
     * @default { tallerThan: "10em", visibleHeight: "6em" }
     */
    topAnchorMessageClamp?: {
        /**
         * Clamp messages taller than this. Supports `px`, `em`, and `rem`.
         *
         * @default "10em"
         */
        tallerThan?: string;
        /**
         * Visible portion of clamped messages. Supports `px`, `em`, and `rem`.
         *
         * @default "6em"
         */
        visibleHeight?: string;
    };
    /**
     * Whether to scroll to bottom when a new run starts.
     *
     * Defaults to true.
     */
    scrollToBottomOnRunStart?: boolean | undefined;
    /**
     * Whether to scroll to bottom when thread history is first loaded.
     *
     * Defaults to true.
     */
    scrollToBottomOnInitialize?: boolean | undefined;
    /**
     * Whether to scroll to bottom when switching to a different thread.
     *
     * Defaults to true.
     */
    scrollToBottomOnThreadSwitch?: boolean | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ThreadPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.div>;
    /**
     * Props for the ThreadPrimitive.Root component.
     * Accepts all standard div element props.
     */
    type Props = ComponentPropsWithoutRef<typeof Primitive.div>;
}
/**
 * The root container component for a thread.
 *
 * This component serves as the foundational wrapper for all thread-related components.
 * It provides the basic structure and context needed for thread functionality.
 *
 * While this component is mounted, an unhandled Escape keydown inside this thread stops its
 * active speech, even if the action bar that started it is no longer mounted. Escape outside
 * every thread retains the document-level fallback.
 *
 * @example
 * ```tsx
 * <ThreadPrimitive.Root>
 *   <ThreadPrimitive.Viewport>
 *     <ThreadPrimitive.Messages>
 *       {() => <MyMessage />}
 *     </ThreadPrimitive.Messages>
 *   </ThreadPrimitive.Viewport>
 * </ThreadPrimitive.Root>
 * ```
 */
export declare const ThreadPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
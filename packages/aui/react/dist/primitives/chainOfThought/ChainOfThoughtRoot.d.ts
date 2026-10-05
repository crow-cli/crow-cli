import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
type PrimitiveDivProps = ComponentPropsWithoutRef<typeof Primitive.div>;
export declare namespace ChainOfThoughtPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = PrimitiveDivProps;
}
/**
 * The root container for chain of thought components.
 *
 * This component provides a wrapper for chain of thought content,
 * including reasoning and tool-call parts that can be collapsed in an accordion.
 *
 * @example
 * ```tsx
 * <ChainOfThoughtPrimitive.Root>
 *   <ChainOfThoughtPrimitive.AccordionTrigger>
 *     Toggle reasoning
 *   </ChainOfThoughtPrimitive.AccordionTrigger>
 *   <ChainOfThoughtPrimitive.Parts />
 * </ChainOfThoughtPrimitive.Root>
 * ```
 */
export declare const ChainOfThoughtPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
export {};
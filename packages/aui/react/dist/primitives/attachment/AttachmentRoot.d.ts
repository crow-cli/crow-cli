import { Primitive } from "../../utils/Primitive.js";
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
type PrimitiveDivProps = ComponentPropsWithoutRef<typeof Primitive.div>;
export declare namespace AttachmentPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.div>;
    /**
     * Props for the AttachmentPrimitive.Root component.
     * Accepts all standard div element props.
     */
    type Props = PrimitiveDivProps;
}
/**
 * The root container component for an attachment.
 *
 * This component provides the foundational wrapper for attachment-related components
 * and content. It serves as the context provider for attachment state and actions.
 *
 * @example
 * ```tsx
 * <AttachmentPrimitive.Root>
 *   <AttachmentPrimitive.Name />
 *   <AttachmentPrimitive.Remove />
 * </AttachmentPrimitive.Root>
 * ```
 */
export declare const AttachmentPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
export {};
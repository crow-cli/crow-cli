import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace MessagePartPrimitiveImage {
    type Element = ComponentRef<typeof Primitive.img>;
    /**
     * Props for the MessagePartPrimitive.Image component.
     * Accepts all standard img element props.
     */
    type Props = ComponentPropsWithoutRef<typeof Primitive.img>;
}
/**
 * Renders an image from the current message part context.
 *
 * This component displays image content from the current message part,
 * automatically setting the src attribute from the message part's image data.
 *
 * @example
 * ```tsx
 * <MessagePartPrimitive.Image
 *   alt="Generated image"
 *   className="message-image"
 *   style={{ maxWidth: '100%' }}
 * />
 * ```
 */
export declare const MessagePartPrimitiveImage: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLImageElement> & import("react").ImgHTMLAttributes<HTMLImageElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLImageElement>, "ref"> & import("react").RefAttributes<HTMLImageElement>>;
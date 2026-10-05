import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ErrorPrimitiveMessage {
    type Element = ComponentRef<typeof Primitive.span>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.span>;
}
export declare const ErrorPrimitiveMessage: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref"> & import("react").RefAttributes<HTMLSpanElement>>;
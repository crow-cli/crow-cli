import { Primitive } from "../../utils/Primitive.js";
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
type PrimitiveDivProps = ComponentPropsWithoutRef<typeof Primitive.div>;
export declare namespace ThreadListPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = PrimitiveDivProps;
}
export declare const ThreadListPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
export {};
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
import { Popover as PopoverPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace AssistantModalPrimitiveContent {
    type Element = ComponentRef<typeof PopoverPrimitive.Content>;
    type Props = WithRenderPropProps<typeof PopoverPrimitive.Content> & {
        portalProps?: ComponentPropsWithoutRef<typeof PopoverPrimitive.Portal> | undefined;
        dissmissOnInteractOutside?: boolean | undefined;
    };
}
export declare const AssistantModalPrimitiveContent: import("react").ForwardRefExoticComponent<Omit<PopoverPrimitive.PopoverContentProps & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & {
    portalProps?: ComponentPropsWithoutRef<typeof PopoverPrimitive.Portal> | undefined;
    dissmissOnInteractOutside?: boolean | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
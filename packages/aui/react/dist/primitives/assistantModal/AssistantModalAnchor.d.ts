import { type ComponentRef } from "react";
import type { Popover as PopoverPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace AssistantModalPrimitiveAnchor {
    type Element = ComponentRef<typeof PopoverPrimitive.Anchor>;
    type Props = WithRenderPropProps<typeof PopoverPrimitive.Anchor>;
}
export declare const AssistantModalPrimitiveAnchor: import("react").ForwardRefExoticComponent<Omit<PopoverPrimitive.PopoverAnchorProps & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
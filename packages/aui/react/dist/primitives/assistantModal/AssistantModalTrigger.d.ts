import { type ComponentRef } from "react";
import type { Popover as PopoverPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace AssistantModalPrimitiveTrigger {
    type Element = ComponentRef<typeof PopoverPrimitive.Trigger>;
    type Props = WithRenderPropProps<typeof PopoverPrimitive.Trigger>;
}
export declare const AssistantModalPrimitiveTrigger: import("react").ForwardRefExoticComponent<Omit<PopoverPrimitive.PopoverTriggerProps & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
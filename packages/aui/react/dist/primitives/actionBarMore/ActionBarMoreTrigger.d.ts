import { type ComponentRef } from "react";
import type { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace ActionBarMorePrimitiveTrigger {
    type Element = ComponentRef<typeof DropdownMenuPrimitive.Trigger>;
    type Props = WithRenderPropProps<typeof DropdownMenuPrimitive.Trigger>;
}
export declare const ActionBarMorePrimitiveTrigger: import("react").ForwardRefExoticComponent<Omit<DropdownMenuPrimitive.DropdownMenuTriggerProps & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
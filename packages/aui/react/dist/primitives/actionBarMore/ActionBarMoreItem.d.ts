import { type ComponentRef } from "react";
import type { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace ActionBarMorePrimitiveItem {
    type Element = ComponentRef<typeof DropdownMenuPrimitive.Item>;
    type Props = WithRenderPropProps<typeof DropdownMenuPrimitive.Item>;
}
export declare const ActionBarMorePrimitiveItem: import("react").ForwardRefExoticComponent<Omit<DropdownMenuPrimitive.DropdownMenuItemProps & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
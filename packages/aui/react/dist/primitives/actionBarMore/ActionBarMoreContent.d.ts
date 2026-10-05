import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace ActionBarMorePrimitiveContent {
    type Element = ComponentRef<typeof DropdownMenuPrimitive.Content>;
    type Props = WithRenderPropProps<typeof DropdownMenuPrimitive.Content> & {
        portalProps?: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Portal> | undefined;
    };
}
export declare const ActionBarMorePrimitiveContent: import("react").ForwardRefExoticComponent<Omit<DropdownMenuPrimitive.DropdownMenuContentProps & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & {
    portalProps?: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Portal> | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
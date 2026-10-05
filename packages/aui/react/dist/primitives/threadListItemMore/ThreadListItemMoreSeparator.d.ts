import { type ComponentRef } from "react";
import type { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type { WithRenderPropProps } from "../../utils/Primitive.js";
export declare namespace ThreadListItemMorePrimitiveSeparator {
    type Element = ComponentRef<typeof DropdownMenuPrimitive.Separator>;
    type Props = WithRenderPropProps<typeof DropdownMenuPrimitive.Separator>;
}
export declare const ThreadListItemMorePrimitiveSeparator: import("react").ForwardRefExoticComponent<Omit<DropdownMenuPrimitive.DropdownMenuSeparatorProps & import("react").RefAttributes<HTMLDivElement>, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>>;
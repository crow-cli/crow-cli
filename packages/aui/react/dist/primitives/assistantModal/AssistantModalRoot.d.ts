import { type FC } from "react";
import { Popover as PopoverPrimitive } from "radix-ui";
export declare namespace AssistantModalPrimitiveRoot {
    type Props = PopoverPrimitive.PopoverProps & {
        unstable_openOnRunStart?: boolean | undefined;
    };
}
export declare const AssistantModalPrimitiveRoot: FC<AssistantModalPrimitiveRoot.Props>;
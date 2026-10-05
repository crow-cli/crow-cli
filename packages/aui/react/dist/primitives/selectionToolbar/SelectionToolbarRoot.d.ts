import { Primitive } from "../../utils/Primitive.js";
import { type ComponentPropsWithoutRef, type ComponentRef } from "react";
type SelectionInfo = {
    text: string;
    messageId: string;
    rect: DOMRect;
};
export declare const useSelectionToolbarInfo: () => SelectionInfo | null;
export declare namespace SelectionToolbarPrimitiveRoot {
    type Element = ComponentRef<typeof Primitive.div>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.div>;
}
/**
 * A floating toolbar that appears when text is selected within a message.
 *
 * Listens for browser selection changes, validates that the selection is
 * within a single message, and renders a positioned portal near the
 * selection. Prevents mousedown from clearing the selection.
 *
 * @example
 * ```tsx
 * <SelectionToolbarPrimitive.Root>
 *   <SelectionToolbarPrimitive.Quote>Quote</SelectionToolbarPrimitive.Quote>
 * </SelectionToolbarPrimitive.Root>
 * ```
 */
export declare const SelectionToolbarPrimitiveRoot: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLDivElement> & import("react").HTMLAttributes<HTMLDivElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLDivElement>, "ref"> & import("react").RefAttributes<HTMLDivElement>>;
export {};
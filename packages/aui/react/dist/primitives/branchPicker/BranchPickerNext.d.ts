import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useBranchPickerNext: () => (() => void) | null;
export declare namespace BranchPickerPrimitiveNext {
    type Element = ActionButtonElement;
    /**
     * Props for the BranchPickerPrimitive.Next component.
     * Inherits all button element props and action button functionality.
     */
    type Props = ActionButtonProps<typeof useBranchPickerNext>;
}
/**
 * A button component that navigates to the next branch in the message tree.
 *
 * This component automatically handles switching to the next available branch
 * and is disabled when there are no more branches to navigate to.
 *
 * @example
 * ```tsx
 * <BranchPickerPrimitive.Next>
 *   Next →
 * </BranchPickerPrimitive.Next>
 * ```
 */
export declare const BranchPickerPrimitiveNext: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};
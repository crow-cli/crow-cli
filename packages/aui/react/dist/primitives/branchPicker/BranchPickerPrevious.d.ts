import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useBranchPickerPrevious: () => (() => void) | null;
export declare namespace BranchPickerPrimitivePrevious {
    type Element = ActionButtonElement;
    /**
     * Props for the BranchPickerPrimitive.Previous component.
     * Inherits all button element props and action button functionality.
     */
    type Props = ActionButtonProps<typeof useBranchPickerPrevious>;
}
/**
 * A button component that navigates to the previous branch in the message tree.
 *
 * This component automatically handles switching to the previous available branch
 * and is disabled when there are no previous branches to navigate to.
 *
 * @example
 * ```tsx
 * <BranchPickerPrimitive.Previous>
 *   ← Previous
 * </BranchPickerPrimitive.Previous>
 * ```
 */
export declare const BranchPickerPrimitivePrevious: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};
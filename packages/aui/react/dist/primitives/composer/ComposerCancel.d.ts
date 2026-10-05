import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useComposerCancel: () => (() => void) | null;
export declare namespace ComposerPrimitiveCancel {
    type Element = ActionButtonElement;
    /**
     * Props for the ComposerPrimitive.Cancel component.
     * Inherits all button element props and action button functionality.
     */
    type Props = ActionButtonProps<typeof useComposerCancel>;
}
/**
 * A button component that cancels the current message composition.
 *
 * This component automatically handles the cancel functionality and is disabled
 * when canceling is not available.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Cancel>
 *   Cancel
 * </ComposerPrimitive.Cancel>
 * ```
 */
export declare const ComposerPrimitiveCancel: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};
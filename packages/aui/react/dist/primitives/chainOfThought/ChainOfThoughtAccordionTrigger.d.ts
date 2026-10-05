import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useChainOfThoughtAccordionTrigger: () => () => void;
export declare namespace ChainOfThoughtPrimitiveAccordionTrigger {
    type Element = ActionButtonElement;
    /**
     * Props for the ChainOfThoughtPrimitive.AccordionTrigger component.
     * Inherits all button element props and action button functionality.
     */
    type Props = ActionButtonProps<typeof useChainOfThoughtAccordionTrigger>;
}
/**
 * A button component that toggles the collapsed state of the chain of thought accordion.
 *
 * This component automatically handles the toggle functionality, expanding or collapsing
 * the chain of thought parts when clicked.
 *
 * @example
 * ```tsx
 * <ChainOfThoughtPrimitive.AccordionTrigger>
 *   Toggle Reasoning
 * </ChainOfThoughtPrimitive.AccordionTrigger>
 * ```
 */
export declare const ChainOfThoughtPrimitiveAccordionTrigger: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};
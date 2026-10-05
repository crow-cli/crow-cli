import { type ActionButtonElement, type ActionButtonProps } from "../../utils/createActionButton.js";
declare const useSuggestionTrigger: ({ send, clearComposer, }: {
    /**
     * When true, automatically sends the message.
     * When false, replaces or appends the composer text with the suggestion - depending on the value of `clearComposer`.
     */
    send?: boolean | undefined;
    /**
     * Whether to clear the composer after sending. A send queued while a run is
     * in progress never clears the composer.
     * When send is set to false, determines if composer text is replaced with suggestion (true, default),
     * or if it's appended to the composer text (false).
     *
     * @default true
     */
    clearComposer?: boolean | undefined;
}) => (() => void) | null;
export declare namespace SuggestionPrimitiveTrigger {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useSuggestionTrigger>;
}
/**
 * A button that triggers the suggestion action (send or insert into composer).
 *
 * @example
 * ```tsx
 * <SuggestionPrimitive.Trigger send>
 *   Click me
 * </SuggestionPrimitive.Trigger>
 * ```
 */
export declare const SuggestionPrimitiveTrigger: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & {
    /**
     * When true, automatically sends the message.
     * When false, replaces or appends the composer text with the suggestion - depending on the value of `clearComposer`.
     */
    send?: boolean | undefined;
    /**
     * Whether to clear the composer after sending. A send queued while a run is
     * in progress never clears the composer.
     * When send is set to false, determines if composer text is replaced with suggestion (true, default),
     * or if it's appended to the composer text (false).
     *
     * @default true
     */
    clearComposer?: boolean | undefined;
} & import("react").RefAttributes<HTMLButtonElement>>;
export {};
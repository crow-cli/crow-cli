import type { ActionButtonElement, ActionButtonProps } from "../../utils/createActionButton.js";
declare const useComposerDictate: () => (() => void) | null;
export declare namespace ComposerPrimitiveDictate {
    type Element = ActionButtonElement;
    type Props = ActionButtonProps<typeof useComposerDictate>;
}
/**
 * A button that starts dictation to convert voice to text.
 *
 * Requires a DictationAdapter to be configured in the runtime.
 *
 * @example
 * ```tsx
 * <ComposerPrimitive.Dictate>
 *   <MicIcon />
 * </ComposerPrimitive.Dictate>
 * ```
 */
export declare const ComposerPrimitiveDictate: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLButtonElement> & import("react").ButtonHTMLAttributes<HTMLButtonElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLButtonElement>, "ref"> & import("react").RefAttributes<HTMLButtonElement>>;
export {};